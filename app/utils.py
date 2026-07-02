import datetime as dt

from sqlalchemy.orm import Session

from . import models


def month_range(month: str) -> tuple[dt.date, dt.date]:
    """Return [start, end) dates for a 'YYYY-MM' month string."""
    year, mon = (int(x) for x in month.split("-"))
    start = dt.date(year, mon, 1)
    end = dt.date(year + 1, 1, 1) if mon == 12 else dt.date(year, mon + 1, 1)
    return start, end


def descendant_category_ids(db: Session, user_id: int, root_id: int) -> set[int]:
    """All category ids under ``root_id`` (inclusive), for a given user.

    Used so a budget set on a parent category counts spend in its
    sub-categories too.
    """
    rows = (
        db.query(models.Category.id, models.Category.parent_id)
        .filter(models.Category.user_id == user_id)
        .all()
    )
    children: dict[int | None, list[int]] = {}
    for cid, pid in rows:
        children.setdefault(pid, []).append(cid)

    result: set[int] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(children.get(current, []))
    return result
