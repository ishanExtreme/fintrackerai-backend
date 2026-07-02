from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..db import get_db

router = APIRouter(prefix="/investments", tags=["investments"])


@router.post("", response_model=schemas.InvestmentOut, status_code=status.HTTP_201_CREATED)
def create_investment(
    payload: schemas.InvestmentCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    inv = models.Investment(
        user_id=user.id,
        month=payload.month,
        category=payload.category,
        amount=payload.amount,
        note=payload.note,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("", response_model=list[schemas.InvestmentOut])
def list_investments(
    month: str | None = Query(default=None, description="Filter by 'YYYY-MM'"),
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.Investment).filter(models.Investment.user_id == user.id)
    if month:
        q = q.filter(models.Investment.month == month)
    elif year:
        q = q.filter(models.Investment.month.like(f"{year}-%"))
    return q.order_by(models.Investment.month.desc(), models.Investment.id.desc()).all()


@router.delete("/{investment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_investment(
    investment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    inv = (
        db.query(models.Investment)
        .filter(models.Investment.id == investment_id, models.Investment.user_id == user.id)
        .first()
    )
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investment not found")
    db.delete(inv)
    db.commit()
    return None
