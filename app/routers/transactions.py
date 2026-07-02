import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..db import get_db
from ..utils import month_range

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
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
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
        q = q.filter(models.Transaction.category_id == category_id)
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
