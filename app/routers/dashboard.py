import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..db import get_db
from ..utils import descendant_category_ids, month_range

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _require_month(month: str) -> tuple[dt.date, dt.date]:
    try:
        return month_range(month)
    except (ValueError, IndexError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "month must be 'YYYY-MM'")


@router.get("/spending", response_model=list[schemas.SpendingRow])
def spending_by_category(
    month: str = Query(..., description="'YYYY-MM'"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Total spend per (leaf) category for the month. Uncategorised rolls up as null."""
    start, end = _require_month(month)

    rows = (
        db.query(
            models.Transaction.category_id,
            func.coalesce(func.sum(models.Transaction.amount), 0.0),
        )
        .filter(
            models.Transaction.user_id == user.id,
            models.Transaction.occurred_on >= start,
            models.Transaction.occurred_on < end,
        )
        .group_by(models.Transaction.category_id)
        .all()
    )

    cats = {
        c.id: c
        for c in db.query(models.Category).filter(models.Category.user_id == user.id).all()
    }

    result: list[schemas.SpendingRow] = []
    for category_id, total in rows:
        cat = cats.get(category_id) if category_id is not None else None
        result.append(
            schemas.SpendingRow(
                category_id=category_id,
                category_name=cat.name if cat else "Uncategorized",
                parent_id=cat.parent_id if cat else None,
                total=float(total),
            )
        )
    result.sort(key=lambda r: r.total, reverse=True)
    return result


@router.get("/budget-status", response_model=list[schemas.BudgetStatusRow])
def budget_status(
    month: str = Query(..., description="'YYYY-MM'"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """For each budget in the month: limit, spent (incl. sub-categories), remaining."""
    start, end = _require_month(month)

    budgets = (
        db.query(models.Budget)
        .filter(models.Budget.user_id == user.id, models.Budget.month == month)
        .all()
    )
    cats = {
        c.id: c
        for c in db.query(models.Category).filter(models.Category.user_id == user.id).all()
    }

    result: list[schemas.BudgetStatusRow] = []
    for b in budgets:
        ids = descendant_category_ids(db, user.id, b.category_id)
        spent = (
            db.query(func.coalesce(func.sum(models.Transaction.amount), 0.0))
            .filter(
                models.Transaction.user_id == user.id,
                models.Transaction.category_id.in_(ids),
                models.Transaction.occurred_on >= start,
                models.Transaction.occurred_on < end,
            )
            .scalar()
        ) or 0.0
        cat = cats.get(b.category_id)
        result.append(
            schemas.BudgetStatusRow(
                category_id=b.category_id,
                category_name=cat.name if cat else "?",
                month=b.month,
                limit_amount=b.limit_amount,
                spent=float(spent),
                remaining=float(b.limit_amount) - float(spent),
            )
        )
    return result


@router.get("/investments", response_model=list[schemas.MonthlyInvestment])
def monthly_investments(
    year: int | None = Query(default=None, description="Defaults to current year"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Total invested per month for a year (amount only — no returns)."""
    target_year = year or dt.date.today().year
    rows = (
        db.query(
            models.Investment.month,
            func.coalesce(func.sum(models.Investment.amount), 0.0),
        )
        .filter(
            models.Investment.user_id == user.id,
            models.Investment.month.like(f"{target_year}-%"),
        )
        .group_by(models.Investment.month)
        .order_by(models.Investment.month)
        .all()
    )
    return [
        schemas.MonthlyInvestment(month=month, total=float(total)) for month, total in rows
    ]
