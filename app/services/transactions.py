"""Transaction service — business logic for transaction operations.

All transaction queries are scoped to the authenticated user. Tools and
routers call these functions instead of building raw queries themselves.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..utils import descendant_category_ids, month_range


def _fmt(x: float) -> str:
    x = float(x)
    return f"{x:,.0f}" if x == int(x) else f"{x:,.2f}"


def _parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _find_category(db: Session, uid: int, name: str, parent_id: int | None = None):
    q = db.query(models.Category).filter(
        models.Category.user_id == uid,
        func.lower(models.Category.name) == name.strip().lower(),
    )
    if parent_id is not None:
        q = q.filter(models.Category.parent_id == parent_id)
    return q.first()


def search_transactions(
    db: Session,
    user_id: int,
    category: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    description: str | None = None,
) -> str:
    """Search past transactions by category, date range, and/or description keyword.

    category: optional category name (includes sub-categories).
    from_date: optional start date 'YYYY-MM-DD' (inclusive).
    to_date: optional end date 'YYYY-MM-DD' (inclusive).
        Defaults to current month if neither is provided.
    description: optional keyword to match against the description and
        subtitle fields (case-insensitive partial match).

    Returns a formatted string with count, total, and list of matching
    expenses with date, category, amount, subtitle, and description.
    """
    today = dt.date.today()

    # Parse dates
    from_dt = _parse_date(from_date)
    to_dt = _parse_date(to_date)

    # Default to current month if no dates provided
    if from_dt is None and to_dt is None:
        start, _ = month_range(today.strftime("%Y-%m"))
        from_dt = start
        to_dt = today
    # If only one date is given, default the other
    elif from_dt is None and to_dt is not None:
        # to_date given, default from_date to 30 days before
        from_dt = to_dt - dt.timedelta(days=30)
    elif to_dt is None and from_dt is not None:
        # from_date given, default to_date to 30 days after
        to_dt = from_dt + dt.timedelta(days=30)

    # Ensure date range is not more than 31 days
    if (to_dt - from_dt).days > 31:
        return (
            "Your date range exceeds 31 days. Please narrow it to one month "
            "(e.g., from 2026-07-01 to 2026-07-31)."
        )

    # Build query
    q = db.query(models.Transaction).filter(
        models.Transaction.user_id == user_id,
        models.Transaction.occurred_on >= from_dt,
        models.Transaction.occurred_on <= to_dt,
    )

    # Apply category filter (includes sub-categories)
    if category:
        cat = _find_category(db, user_id, category)
        if cat:
            cat_ids = descendant_category_ids(db, user_id, cat.id)
            q = q.filter(models.Transaction.category_id.in_(list(cat_ids)))
        # If category not found, skip category filter (search all)

    # Apply description/keyword filter
    if description:
        keyword = f"%{description.strip()}%"
        q = q.filter(
            (func.lower(models.Transaction.description).like(func.lower(keyword)))
            | (func.lower(models.Transaction.subtitle).like(func.lower(keyword)))
        )

    expenses = q.order_by(models.Transaction.occurred_on.desc()).all()

    if not expenses:
        scope = ""
        if from_dt and to_dt:
            scope = f" between {from_dt.isoformat()} and {to_dt.isoformat()}"
            if category:
                scope += f" in {category}"
        elif category:
            scope = f" in {category}"
        return f"No expenses found{scope}."

    # Format results
    total = sum(e.amount for e in expenses)
    lines = [
        f"You have {len(expenses)} expense{'s' if len(expenses) != 1 else ''}"
        f", totaling ₹{_fmt(total)}."
    ]

    for exp in expenses:
        date_str = exp.occurred_on.isoformat()
        cat_name = ""
        if exp.category_id:
            cat = db.get(models.Category, exp.category_id)
            cat_name = f" ({cat.name})" if cat else ""
        parts = [f"  • {date_str}: ₹{_fmt(exp.amount)}{cat_name}"]
        if exp.subtitle:
            parts[-1] += f' — "{exp.subtitle}"'
        if exp.description:
            parts[-1] += f" — {exp.description}"
        lines.append(parts[0])

    return "\n".join(lines)