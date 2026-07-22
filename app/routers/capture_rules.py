"""Capture rules ("remember") — user-taught auto-labeling for SMS captures."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..db import get_db
from ..services import capture_rules as rules_svc

router = APIRouter(prefix="/capture-rules", tags=["capture-rules"])


@router.get("", response_model=list[schemas.CaptureRuleOut])
def list_rules(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.CaptureRule)
        .filter(models.CaptureRule.user_id == user.id)
        .order_by(models.CaptureRule.id.desc())
        .all()
    )


@router.post("", response_model=schemas.CaptureRuleResult, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: schemas.CaptureRuleIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if payload.kind == "payee":
        if not (payload.match_value and payload.match_value.strip()):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "payee rule needs a match_value"
            )
    elif payload.kind == "location":
        if payload.lat is None or payload.lng is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "location rule needs lat and lng"
            )

    if payload.category_id is not None:
        owned = (
            db.query(models.Category)
            .filter(
                models.Category.id == payload.category_id,
                models.Category.user_id == user.id,
            )
            .first()
        )
        if not owned:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown category_id")

    rule = models.CaptureRule(
        user_id=user.id,
        kind=payload.kind,
        match_value=(payload.match_value or "").strip() or None,
        lat=payload.lat,
        lng=payload.lng,
        radius_m=payload.radius_m or (rules_svc.DEFAULT_RADIUS_M if payload.kind == "location" else None),
        location_name=(payload.location_name or "").strip() or None,
        category_id=payload.category_id,
        subtitle=(payload.subtitle or "").strip() or None,
    )
    db.add(rule)
    db.flush()  # assign id before re-apply

    applied = rules_svc.reapply_rule(db, user.id, rule)
    db.commit()
    db.refresh(rule)
    return schemas.CaptureRuleResult(
        rule=schemas.CaptureRuleOut.model_validate(rule), applied=applied
    )


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    rule = (
        db.query(models.CaptureRule)
        .filter(
            models.CaptureRule.id == rule_id,
            models.CaptureRule.user_id == user.id,
        )
        .first()
    )
    if rule:
        db.delete(rule)
        db.commit()
    return None
