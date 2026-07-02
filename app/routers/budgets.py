from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..db import get_db

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.put("", response_model=schemas.BudgetOut)
def upsert_budget(
    payload: schemas.BudgetUpsert,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cat = (
        db.query(models.Category.id)
        .filter(models.Category.id == payload.category_id, models.Category.user_id == user.id)
        .first()
    )
    if not cat:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown category_id")

    budget = (
        db.query(models.Budget)
        .filter(
            models.Budget.user_id == user.id,
            models.Budget.category_id == payload.category_id,
            models.Budget.month == payload.month,
        )
        .first()
    )
    if budget:
        budget.limit_amount = payload.limit_amount
    else:
        budget = models.Budget(
            user_id=user.id,
            category_id=payload.category_id,
            month=payload.month,
            limit_amount=payload.limit_amount,
        )
        db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


@router.get("", response_model=list[schemas.BudgetOut])
def list_budgets(
    month: str | None = Query(default=None, description="Filter by 'YYYY-MM'"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.Budget).filter(models.Budget.user_id == user.id)
    if month:
        q = q.filter(models.Budget.month == month)
    return q.order_by(models.Budget.month.desc()).all()


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    budget = (
        db.query(models.Budget)
        .filter(models.Budget.id == budget_id, models.Budget.user_id == user.id)
        .first()
    )
    if not budget:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Budget not found")
    db.delete(budget)
    db.commit()
    return None
