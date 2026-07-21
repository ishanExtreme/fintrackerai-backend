"""Capture rules ("remember") — auto-label recurring payees/places.

Two rule kinds:
- ``payee``   : match a transaction's ``counterparty`` → set category + subtitle.
- ``location``: match capture coords within a geofence → set a place label
                (and, only if no payee rule matched, a fallback category).

Matches pre-correct a capture but leave ``reviewed=False`` (it still shows in
the Auto tab for a final tick). Payee rules win over location rules for category.
"""

from __future__ import annotations

import math

from sqlalchemy.orm import Session

from .. import models

DEFAULT_RADIUS_M = 150.0


def normalize(s: str | None) -> str:
    return (s or "").strip().lower()


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def payee_matches(rule: models.CaptureRule, counterparty: str | None) -> bool:
    if rule.kind != "payee" or not rule.match_value or not counterparty:
        return False
    a, b = normalize(counterparty), normalize(rule.match_value)
    if not b:
        return False
    return a == b or b in a or a in b


def location_matches(
    rule: models.CaptureRule, lat: float | None, lng: float | None
) -> bool:
    if rule.kind != "location" or lat is None or lng is None:
        return False
    if rule.lat is None or rule.lng is None:
        return False
    radius = rule.radius_m or DEFAULT_RADIUS_M
    return haversine_m(lat, lng, rule.lat, rule.lng) <= radius


def resolve_overrides(
    db: Session,
    user_id: int,
    *,
    counterparty: str | None,
    lat: float | None,
    lng: float | None,
) -> dict:
    """Compute field overrides from all of a user's rules for one capture.

    Returns a dict possibly containing:
    - ``category_id`` — authoritative (payee rule),
    - ``subtitle``    — payee rule label,
    - ``location_label`` — location rule place name,
    - ``location_category_id`` — location rule's *fallback* category (apply only
      when the capture has no category and no payee rule matched).
    Empty if nothing matched.
    """
    rules = (
        db.query(models.CaptureRule)
        .filter(models.CaptureRule.user_id == user_id)
        .all()
    )
    overrides: dict = {}

    # Location: supplies the place label + a fallback category.
    for rule in rules:
        if location_matches(rule, lat, lng):
            if rule.location_name:
                overrides["location_label"] = rule.location_name
            if rule.category_id is not None:
                overrides["location_category_id"] = rule.category_id
            break

    # Payee: authoritative category + subtitle.
    for rule in rules:
        if payee_matches(rule, counterparty):
            if rule.category_id is not None:
                overrides["category_id"] = rule.category_id
            if rule.subtitle:
                overrides["subtitle"] = rule.subtitle
            break

    return overrides


def _apply_rule_to_txn(rule: models.CaptureRule, txn: models.Transaction) -> bool:
    """Mutate *txn* per *rule* if it matches; return whether anything changed."""
    if rule.kind == "payee" and payee_matches(rule, txn.counterparty):
        changed = False
        if rule.category_id is not None:
            txn.category_id = rule.category_id
            changed = True
        if rule.subtitle:
            txn.subtitle = rule.subtitle
            changed = True
        return changed
    if rule.kind == "location" and location_matches(rule, txn.lat, txn.lng):
        changed = False
        if rule.location_name:
            txn.location_label = rule.location_name
            changed = True
        # Location category is a fallback: only when the capture has none.
        if rule.category_id is not None and txn.category_id is None:
            txn.category_id = rule.category_id
            changed = True
        return changed
    return False


def reapply_rule(db: Session, user_id: int, rule: models.CaptureRule) -> int:
    """Apply a newly-created rule to the user's existing *unreviewed* SMS
    captures. Returns the number of transactions updated. Caller commits.
    """
    rows = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.source == "sms",
            models.Transaction.reviewed == False,  # noqa: E712
        )
        .all()
    )
    return sum(1 for txn in rows if _apply_rule_to_txn(rule, txn))
