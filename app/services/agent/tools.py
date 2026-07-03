"""Finance tools the specialist nodes call.

These **mutate the database**, scoped to the authenticated user via `runtime`
context vars. Each returns a short natural-language result the node/orchestrator
speaks, and emits a structured `ChatEvent` for the app to render.
"""

from __future__ import annotations

import datetime as dt

from langchain_core.tools import tool
from sqlalchemy import func

from ... import models
from ...utils import descendant_category_ids, month_range
from .runtime import current_db, current_today, current_user_id, record_event


# ------------------------------- helpers ------------------------------- #
def _current_month() -> str:
    return current_today().strftime("%Y-%m")


def format_user_categories(db, uid) -> str:
    """A plain-text view of the user's category tree, for prompt context.

    Indentation shows nesting (sub-categories under their parent), so the model
    can both reuse existing categories and mirror the user's own organisation
    when it must create a new one. Returns "" if the user has no categories yet.
    """
    cats = (
        db.query(models.Category)
        .filter(models.Category.user_id == uid)
        .order_by(models.Category.name)
        .all()
    )
    if not cats:
        return ""

    ids = {c.id for c in cats}
    children: dict[int | None, list] = {}
    for c in cats:
        parent = c.parent_id if c.parent_id in ids else None
        children.setdefault(parent, []).append(c)

    lines: list[str] = []

    def walk(parent_id, depth):
        for c in sorted(children.get(parent_id, []), key=lambda x: x.name.lower()):
            lines.append(f"{'  ' * depth}- {c.name}")
            walk(c.id, depth + 1)

    walk(None, 0)
    return "The user's existing categories (indentation = sub-category):\n" + "\n".join(lines)


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


def _find_category(db, uid, name, parent_id=None):
    q = db.query(models.Category).filter(
        models.Category.user_id == uid,
        func.lower(models.Category.name) == name.strip().lower(),
    )
    if parent_id is not None:
        q = q.filter(models.Category.parent_id == parent_id)
    return q.first()


def _resolve_or_create_category(db, uid, name, parent_name=None, ctype="expense"):
    parent_id = None
    if parent_name:
        parent = _find_category(db, uid, parent_name)
        if not parent:
            parent = models.Category(
                user_id=uid, name=parent_name.strip(), type=ctype, tags=[], created_by="llm"
            )
            db.add(parent)
            db.flush()
        parent_id = parent.id
    cat = _find_category(db, uid, name, parent_id=parent_id)
    if not cat:
        cat = models.Category(
            user_id=uid,
            name=name.strip(),
            parent_id=parent_id,
            type=ctype,
            tags=[],
            created_by="llm",
        )
        db.add(cat)
        db.flush()
    return cat


def _spent(db, uid, category_ids, month) -> float:
    start, end = month_range(month)
    total = (
        db.query(func.coalesce(func.sum(models.Transaction.amount), 0.0))
        .filter(
            models.Transaction.user_id == uid,
            models.Transaction.category_id.in_(list(category_ids)),
            models.Transaction.occurred_on >= start,
            models.Transaction.occurred_on < end,
        )
        .scalar()
    )
    return float(total or 0.0)


def _budget_warning_text(db, uid, category_id, month) -> str:
    """Check the category and its ancestors for a breached/near budget."""
    chain: list[int] = []
    cid = category_id
    seen: set[int] = set()
    while cid and cid not in seen:
        seen.add(cid)
        cat = db.get(models.Category, cid)
        if not cat or cat.user_id != uid:
            break
        chain.append(cat.id)
        cid = cat.parent_id

    for bid in chain:
        budget = (
            db.query(models.Budget)
            .filter_by(user_id=uid, category_id=bid, month=month)
            .first()
        )
        if not budget:
            continue
        spent = _spent(db, uid, descendant_category_ids(db, uid, bid), month)
        cat = db.get(models.Category, bid)
        remaining = budget.limit_amount - spent
        if spent > budget.limit_amount:
            record_event(
                "budget_warning", category=cat.name, month=month, spent=spent,
                limit=budget.limit_amount, remaining=remaining, state="over",
            )
            return (
                f"Heads up: you're over your {cat.name} budget — "
                f"₹{_fmt(spent)} of ₹{_fmt(budget.limit_amount)} (₹{_fmt(-remaining)} over)."
            )
        if spent >= 0.9 * budget.limit_amount:
            record_event(
                "budget_warning", category=cat.name, month=month, spent=spent,
                limit=budget.limit_amount, remaining=remaining, state="near",
            )
            return (
                f"Heads up: you've used ₹{_fmt(spent)} of your ₹{_fmt(budget.limit_amount)} "
                f"{cat.name} budget — ₹{_fmt(remaining)} left."
            )
    return ""


# ------------------------------- tools ------------------------------- #
@tool
def add_expense(
    amount: float,
    category: str,
    parent_category: str | None = None,
    date: str | None = None,
    note: str | None = None,
) -> str:
    """Record a spend/expense.

    amount: rupees spent (positive number).
    category: category name, e.g. "Food" or "Movie tickets". Created if it's new.
    parent_category: optional parent to nest a new sub-category under, e.g.
        category "Movie tickets" with parent_category "Personal".
    date: optional 'YYYY-MM-DD'; defaults to today.
    note: optional short note such as the merchant or item.
    """
    db, uid = current_db(), current_user_id()
    cat = _resolve_or_create_category(db, uid, category, parent_category)
    occurred = _parse_date(date) or current_today()
    txn = models.Transaction(
        user_id=uid, category_id=cat.id, amount=float(amount),
        currency="INR", occurred_on=occurred, note=note, source="chat",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    record_event(
        "transaction_created", id=txn.id, amount=float(amount),
        category=cat.name, date=occurred.isoformat(),
    )
    msg = f"Recorded ₹{_fmt(amount)} under {cat.name} on {occurred.isoformat()}."
    warn = _budget_warning_text(db, uid, cat.id, occurred.strftime("%Y-%m"))
    return f"{msg} {warn}".strip()


@tool
def delete_expenses(category: str, month: str | None = None, date: str | None = None) -> str:
    """Delete recorded expenses in ONE category, scoped to a month or a single day.

    category: REQUIRED — the category whose expenses to delete (its sub-categories
        are included too).
    month: optional 'YYYY-MM' — delete that whole month's expenses in the category.
    date: optional 'YYYY-MM-DD' — delete only that day's expenses in the category
        (takes precedence over month). If neither is given, the current month is used.

    IMPORTANT: this only ever deletes within a single named category. It CANNOT
    wipe an entire month across all categories, nor delete all expenses — if the
    user asks for that, do NOT call this tool; tell them to open
    Settings → Reset expenses to do it themselves.
    """
    db, uid = current_db(), current_user_id()
    cat = _find_category(db, uid, category)
    if not cat:
        return f"You have no category named {category}, so there's nothing to delete."

    cat_ids = descendant_category_ids(db, uid, cat.id)
    q = db.query(models.Transaction).filter(
        models.Transaction.user_id == uid,
        models.Transaction.category_id.in_(list(cat_ids)),
    )
    day = _parse_date(date)
    if day:
        q = q.filter(models.Transaction.occurred_on == day)
        scope = f"on {day.isoformat()}"
    else:
        m = month or _current_month()
        try:
            start, end = month_range(m)
        except (ValueError, IndexError):
            return f"{m!r} isn't a valid month — use YYYY-MM."
        q = q.filter(
            models.Transaction.occurred_on >= start, models.Transaction.occurred_on < end
        )
        scope = f"in {m}"

    count = q.count()
    if count == 0:
        return f"No {cat.name} expenses found {scope}."
    q.delete(synchronize_session=False)
    db.commit()
    record_event("expenses_deleted", category=cat.name, scope=scope, count=count)
    return f"Deleted {count} {cat.name} expense{'s' if count != 1 else ''} {scope}."


@tool
def find_or_create_category(
    name: str, parent_category: str | None = None
) -> str:
    """Create (or find) a spending category, optionally nested under a parent.

    Use this to organise categories, e.g. create "Movie tickets" under "Personal".
    """
    db, uid = current_db(), current_user_id()
    cat = _resolve_or_create_category(db, uid, name, parent_category)
    db.commit()
    parent = db.get(models.Category, cat.parent_id) if cat.parent_id else None
    where = f" under {parent.name}" if parent else ""
    return f"Category {cat.name}{where} is ready."


@tool
def query_spending(category: str | None = None, month: str | None = None) -> str:
    """How much was spent. category optional (name; includes its sub-categories);
    month optional 'YYYY-MM' (defaults to the current month)."""
    db, uid = current_db(), current_user_id()
    month = month or _current_month()
    if category:
        cat = _find_category(db, uid, category)
        if not cat:
            return f"You have no category named {category}."
        total = _spent(db, uid, descendant_category_ids(db, uid, cat.id), month)
        return f"You spent ₹{_fmt(total)} on {cat.name} in {month}."
    start, end = month_range(month)
    total = (
        db.query(func.coalesce(func.sum(models.Transaction.amount), 0.0))
        .filter(
            models.Transaction.user_id == uid,
            models.Transaction.occurred_on >= start,
            models.Transaction.occurred_on < end,
        )
        .scalar()
    ) or 0.0
    return f"You spent ₹{_fmt(total)} in total in {month}."


@tool
def set_budget(category: str, limit: float, month: str | None = None) -> str:
    """Set a monthly spending budget (limit) for a category. month optional
    'YYYY-MM' (defaults to the current month)."""
    db, uid = current_db(), current_user_id()
    month = month or _current_month()
    cat = _resolve_or_create_category(db, uid, category)
    budget = (
        db.query(models.Budget)
        .filter_by(user_id=uid, category_id=cat.id, month=month)
        .first()
    )
    if budget:
        budget.limit_amount = float(limit)
    else:
        budget = models.Budget(
            user_id=uid, category_id=cat.id, month=month, limit_amount=float(limit)
        )
        db.add(budget)
    db.commit()
    record_event("budget_set", category=cat.name, month=month, limit=float(limit))
    return f"Set a ₹{_fmt(limit)} budget for {cat.name} in {month}."


@tool
def query_budget_remaining(category: str, month: str | None = None) -> str:
    """How much budget is left for a category (includes its sub-categories).
    month optional 'YYYY-MM' (defaults to the current month)."""
    db, uid = current_db(), current_user_id()
    month = month or _current_month()
    cat = _find_category(db, uid, category)
    if not cat:
        return f"You have no category named {category}."
    budget = (
        db.query(models.Budget)
        .filter_by(user_id=uid, category_id=cat.id, month=month)
        .first()
    )
    if not budget:
        return f"No budget is set for {cat.name} in {month}."
    spent = _spent(db, uid, descendant_category_ids(db, uid, cat.id), month)
    remaining = budget.limit_amount - spent
    if remaining < 0:
        return (
            f"You're over your {cat.name} budget for {month}: spent ₹{_fmt(spent)} "
            f"of ₹{_fmt(budget.limit_amount)} (₹{_fmt(-remaining)} over)."
        )
    return (
        f"You have ₹{_fmt(remaining)} left for {cat.name} in {month} "
        f"(spent ₹{_fmt(spent)} of ₹{_fmt(budget.limit_amount)})."
    )


@tool
def add_investment(
    amount: float,
    month: str | None = None,
    category: str | None = None,
    note: str | None = None,
) -> str:
    """Record how much was invested in a month (amount only — no returns tracked).

    category: optional label, e.g. "mutual funds" or "stocks".
    month: optional 'YYYY-MM'; defaults to the current month.
    """
    db, uid = current_db(), current_user_id()
    month = month or _current_month()
    inv = models.Investment(
        user_id=uid, month=month, category=category, amount=float(amount), note=note
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    record_event(
        "investment_added", id=inv.id, amount=float(amount), month=month, category=category
    )
    label = f" in {category}" if category else ""
    return f"Recorded ₹{_fmt(amount)} invested{label} for {month}."


@tool
def query_investments(month: str | None = None, year: int | None = None) -> str:
    """Total invested. Provide month ('YYYY-MM') for one month, else year
    (defaults to the current year)."""
    db, uid = current_db(), current_user_id()
    if month:
        total = (
            db.query(func.coalesce(func.sum(models.Investment.amount), 0.0))
            .filter(models.Investment.user_id == uid, models.Investment.month == month)
            .scalar()
        ) or 0.0
        return f"You invested ₹{_fmt(total)} in {month}."
    y = year or current_today().year
    total = (
        db.query(func.coalesce(func.sum(models.Investment.amount), 0.0))
        .filter(models.Investment.user_id == uid, models.Investment.month.like(f"{y}-%"))
        .scalar()
    ) or 0.0
    return f"You invested ₹{_fmt(total)} in {y}."
