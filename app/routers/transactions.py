import asyncio
import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..crypto import resolve_sms_llm_key, resolve_sms_llm_model
from ..db import get_db
from ..services import capture_rules
from ..services.agent.runtime import request_scope
from ..services.agent.tools import _resolve_or_create_category as resolve_or_create_category
from ..services.sms_capture import extract_with_context
from ..utils import descendant_category_ids, month_range

logger = logging.getLogger("transactions")

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _get_owned_txn(db: Session, user_id: int, txn_id: int) -> models.Transaction:
    txn = (
        db.query(models.Transaction)
        .filter(models.Transaction.id == txn_id, models.Transaction.user_id == user_id)
        .first()
    )
    if not txn:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return txn


def _validate_category(db: Session, user_id: int, category_id: int | None) -> None:
    if category_id is None:
        return
    exists = (
        db.query(models.Category.id)
        .filter(models.Category.id == category_id, models.Category.user_id == user_id)
        .first()
    )
    if not exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown category_id")


@router.post("", response_model=schemas.TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: schemas.TransactionCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _validate_category(db, user.id, payload.category_id)
    txn = models.Transaction(
        user_id=user.id,
        category_id=payload.category_id,
        amount=payload.amount,
        currency=payload.currency,
        occurred_on=payload.occurred_on or dt.date.today(),
        note=payload.note,
        source=payload.source if payload.source in {"chat", "sms", "manual"} else "manual",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.get("", response_model=list[schemas.TransactionOut])
def list_transactions(
    month: str | None = Query(default=None, description="Filter by 'YYYY-MM'"),
    category_id: int | None = Query(default=None),
    include_children: bool = Query(
        default=False,
        description="If true, also include transactions for sub-categories "
        "of the given category_id",
    ),
    source: str | None = Query(
        default=None,
        description="Filter by source ('chat', 'sms', 'manual')",
    ),
    reviewed: bool | None = Query(
        default=None,
        description="Filter by reviewed status (true = reviewed, false = unreviewed)",
    ),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """List transactions with optional filters.
    
    - ``month``: filter by 'YYYY-MM'
    - ``category_id``: filter by category (when combined with 
      ``include_children=true``, includes sub-categories too)
    """
    q = db.query(models.Transaction).filter(models.Transaction.user_id == user.id)
    if month:
        try:
            start, end = month_range(month)
        except (ValueError, IndexError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "month must be 'YYYY-MM'")
        q = q.filter(
            models.Transaction.occurred_on >= start, models.Transaction.occurred_on < end
        )
    if category_id is not None:
        if include_children:
            ids = descendant_category_ids(db, user.id, category_id)
            q = q.filter(models.Transaction.category_id.in_(list(ids)))
        else:
            q = q.filter(models.Transaction.category_id == category_id)
    if source is not None:
        q = q.filter(models.Transaction.source == source)
    if reviewed is not None:
        q = q.filter(models.Transaction.reviewed == reviewed)
    return q.order_by(models.Transaction.occurred_on.desc(), models.Transaction.id.desc()).all()


@router.patch("/{txn_id}", response_model=schemas.TransactionOut)
def update_transaction(
    txn_id: int,
    payload: schemas.TransactionUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    txn = _get_owned_txn(db, user.id, txn_id)
    data = payload.model_dump(exclude_unset=True)
    if "category_id" in data:
        _validate_category(db, user.id, data["category_id"])
    for field, value in data.items():
        setattr(txn, field, value)
    db.commit()
    db.refresh(txn)
    return txn


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    txn_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    txn = _get_owned_txn(db, user.id, txn_id)
    db.delete(txn)
    db.commit()
    return None


@router.delete("", response_model=schemas.TransactionDeleteResult)
def delete_transactions(
    month: str | None = Query(default=None, description="Delete within a 'YYYY-MM' month"),
    all: bool = Query(default=False, description="Delete every transaction (no other filters)"),
    category_id: int | None = Query(
        default=None, description="Scope to a category (includes its sub-categories)"
    ),
    uncategorized: bool = Query(
        default=False, description="Scope to transactions with no category"
    ),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Bulk-delete the user's transactions — the app's "reset expenses" action.

    Either ``all=true`` (everything, no other filter) or ``month`` is required.
    Within a month you may further scope by ``category_id`` (that category and its
    sub-categories) or ``uncategorized=true`` (transactions with no category);
    those two are mutually exclusive. Destructive and irreversible; the app
    double-confirms before calling this.
    """
    if category_id is not None and uncategorized:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "'category_id' and 'uncategorized' are mutually exclusive",
        )

    q = db.query(models.Transaction).filter(models.Transaction.user_id == user.id)

    if all:
        if month or category_id is not None or uncategorized:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "'all=true' cannot be combined with other filters"
            )
    else:
        if not month:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Provide 'month' (optionally scoped), or 'all=true'"
            )
        try:
            start, end = month_range(month)
        except (ValueError, IndexError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "month must be 'YYYY-MM'")
        q = q.filter(
            models.Transaction.occurred_on >= start, models.Transaction.occurred_on < end
        )
        if category_id is not None:
            _validate_category(db, user.id, category_id)  # 400 if not owned
            ids = descendant_category_ids(db, user.id, category_id)
            q = q.filter(models.Transaction.category_id.in_(list(ids)))
        elif uncategorized:
            q = q.filter(models.Transaction.category_id.is_(None))

    deleted = q.delete(synchronize_session=False)
    db.commit()
    return schemas.TransactionDeleteResult(deleted=deleted)


@router.post("/ingest", response_model=schemas.SmsIngestResult)
def ingest_sms(
    payload: schemas.SmsIngest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Accept a structured, on-device-parsed SMS/notification payload.

    Only structured fields arrive here — never raw SMS text. Credits are
    skipped (expense-focused for now); debits are deduped on ``raw_hash``.
    """
    if payload.direction != "debit":
        return schemas.SmsIngestResult(status="skipped")

    existing = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user.id,
            models.Transaction.raw_ref == payload.raw_hash,
        )
        .first()
    )
    if existing:
        return schemas.SmsIngestResult(
            status="duplicate", transaction=schemas.TransactionOut.model_validate(existing)
        )

    _validate_category(db, user.id, payload.category_id)
    note = payload.merchant
    if payload.account_masked:
        note = f"{note} ({payload.account_masked})" if note else payload.account_masked

    txn = models.Transaction(
        user_id=user.id,
        category_id=payload.category_id,
        amount=payload.amount,
        currency="INR",
        occurred_on=payload.occurred_on or dt.date.today(),
        note=note,
        source="sms",
        raw_ref=payload.raw_hash,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return schemas.SmsIngestResult(
        status="created", transaction=schemas.TransactionOut.model_validate(txn)
    )


@router.post("/capture", response_model=schemas.SmsCaptureResult)
async def capture_sms(
    payload: schemas.SmsCapture,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Capture an expense from raw SMS text using LLM extraction.

    Flow:
    1. Dedupe on ``raw_hash`` → ``status="duplicate"``
    2. LLM extract (own SMS key, cheaper model) → ``is_expense=False`` → ``skipped``
    3. Resolve/create category; insert Transaction → ``status="created"``

    Returns 200 in all cases (including ``skipped`` on no-key / extraction
    failure) so the mobile queue drains the item instead of retrying forever.
    """
    existing = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user.id,
            models.Transaction.raw_ref == payload.raw_hash,
        )
        .first()
    )
    if existing:
        return schemas.SmsCaptureResult(
            status="duplicate",
            transaction=schemas.TransactionOut.model_validate(existing),
        )

    # Run the (blocking) extractor in a worker thread inside a request scope so
    # get_model() picks up the key. to_thread propagates the contextvars.
    sms_key = resolve_sms_llm_key(db, user)
    if not sms_key:
        logger.warning("SMS capture skipped for user %s: no LLM key available", user.id)
        return schemas.SmsCaptureResult(status="skipped")
    sms_model = resolve_sms_llm_model(db, user)

    try:
        with request_scope(db=db, user_id=user.id, llm_key=sms_key):
            extraction = await asyncio.to_thread(
                extract_with_context,
                db=db,
                user_id=user.id,
                sms_text=payload.sms_text,
                sender=payload.sender,
                received_at=payload.received_at,
                place_label=payload.place_label,
                model_override=sms_model,
            )
    except Exception as e:
        logger.error("SMS extraction failed: %s", e)
        return schemas.SmsCaptureResult(status="skipped")

    if not extraction.get("is_expense"):
        return schemas.SmsCaptureResult(status="skipped")

    # Reuse the agent's resolver for parity with the chat agent.
    category_name = extraction["category"]
    parent_name = extraction.get("parent_category")
    if not category_name or category_name == "Uncategorized":
        category_id = None
    else:
        cat = resolve_or_create_category(db, user.id, category_name, parent_name)
        category_id = cat.id

    occurred_on = extraction.get("occurred_on") or dt.date.today()
    counterparty = extraction.get("counterparty")
    subtitle = extraction.get("subtitle")
    location_label = payload.place_label

    # "Remember" rules — pre-correct known payees/places (still reviewed=False).
    overrides = capture_rules.resolve_overrides(
        db, user.id, counterparty=counterparty, lat=payload.lat, lng=payload.lng
    )
    if overrides.get("category_id") is not None:
        category_id = overrides["category_id"]  # payee rule is authoritative
    elif category_id is None and overrides.get("location_category_id") is not None:
        category_id = overrides["location_category_id"]  # location fallback
    if overrides.get("subtitle"):
        subtitle = overrides["subtitle"]
    if overrides.get("location_label"):
        location_label = overrides["location_label"]

    txn = models.Transaction(
        user_id=user.id,
        category_id=category_id,
        amount=extraction["amount"],
        currency="INR",
        occurred_on=occurred_on,
        subtitle=subtitle,
        description=extraction.get("description"),
        note=extraction.get("note"),
        source="sms",
        raw_ref=payload.raw_hash,
        confidence=extraction.get("confidence"),
        reviewed=False,
        lat=payload.lat,
        lng=payload.lng,
        location_label=location_label,
        counterparty=counterparty,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    return schemas.SmsCaptureResult(
        status="created", transaction=schemas.TransactionOut.model_validate(txn)
    )


@router.post("/review-batch", response_model=schemas.ReviewBatchResult)
def review_batch(
    payload: schemas.ReviewBatchRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Mark SMS transactions as reviewed in bulk.

    Accepts either:
    - ``ids``: specific transaction IDs to mark reviewed
    - ``month``: all unreviewed SMS transactions for a given month
    """
    if payload.ids:
        count = (
            db.query(models.Transaction)
            .filter(
                models.Transaction.id.in_(payload.ids),
                models.Transaction.user_id == user.id,
                models.Transaction.source == "sms",
            )
            .update({models.Transaction.reviewed: True}, synchronize_session=False)
        )
    elif payload.month:
        try:
            start, end = month_range(payload.month)
        except (ValueError, IndexError):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "month must be 'YYYY-MM'"
            )
        count = (
            db.query(models.Transaction)
            .filter(
                models.Transaction.user_id == user.id,
                models.Transaction.source == "sms",
                models.Transaction.reviewed == False,  # noqa: E712
                models.Transaction.occurred_on >= start,
                models.Transaction.occurred_on < end,
            )
            .update({models.Transaction.reviewed: True}, synchronize_session=False)
        )
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Provide either 'ids' or 'month'",
        )

    db.commit()
    return schemas.ReviewBatchResult(updated=count)
