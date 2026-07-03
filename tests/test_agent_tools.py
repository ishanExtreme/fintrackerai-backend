"""Unit tests for the agent's finance tools (pure DB logic — no LLM)."""

import datetime as dt

from app import models
from app.db import SessionLocal
from app.seed import seed_default_categories
from app.services.agent import tools
from app.services.agent.runtime import request_scope

JULY = dt.date(2026, 7, 3)


def _mk_user(db):
    u = models.User(firebase_uid="tool-user", email="t@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    seed_default_categories(db, u.id)
    return u


def test_add_expense_records_transaction():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            out = tools.add_expense.invoke(
                {"amount": 500, "category": "Food", "note": "biryani"}
            )
        assert "Food" in out
        txns = db.query(models.Transaction).filter_by(user_id=u.id).all()
        assert len(txns) == 1
        assert txns[0].amount == 500
        assert txns[0].source == "chat"
        assert txns[0].occurred_on == JULY
    finally:
        db.close()


def test_add_expense_creates_subcategory_under_parent():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            tools.add_expense.invoke(
                {
                    "amount": 1200,
                    "category": "Movie tickets",
                    "parent_category": "Personal",
                    "date": "2026-07-05",
                }
            )
        cat = (
            db.query(models.Category)
            .filter_by(user_id=u.id, name="Movie tickets")
            .first()
        )
        assert cat is not None
        assert cat.created_by == "llm"
        parent = db.get(models.Category, cat.parent_id)
        assert parent.name == "Personal"
    finally:
        db.close()


def test_add_expense_emits_budget_warning_when_near_limit():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY) as events:
            tools.set_budget.invoke({"category": "Food", "limit": 600, "month": "2026-07"})
            out = tools.add_expense.invoke(
                {"amount": 580, "category": "Food", "date": "2026-07-03"}
            )
        assert "budget" in out.lower()
        assert any(e.type == "budget_warning" for e in events)
    finally:
        db.close()


def test_set_and_query_budget_remaining_rolls_up_subcategories():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            tools.set_budget.invoke({"category": "Personal", "limit": 5000, "month": "2026-07"})
            tools.add_expense.invoke(
                {
                    "amount": 1200,
                    "category": "Movie tickets",
                    "parent_category": "Personal",
                    "date": "2026-07-05",
                }
            )
            out = tools.query_budget_remaining.invoke(
                {"category": "Personal", "month": "2026-07"}
            )
        assert "3,800" in out  # 5000 - 1200 (sub-category counts against parent)
    finally:
        db.close()


def test_delete_expenses_scoped_to_category_and_month():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY) as events:
            tools.add_expense.invoke({"amount": 500, "category": "Food", "date": "2026-07-03"})
            tools.add_expense.invoke({"amount": 700, "category": "Food", "date": "2026-07-20"})
            tools.add_expense.invoke({"amount": 900, "category": "Food", "date": "2026-08-01"})
            tools.add_expense.invoke({"amount": 300, "category": "Transport", "date": "2026-07-04"})
            out = tools.delete_expenses.invoke({"category": "Food", "month": "2026-07"})

        assert "2" in out and "Food" in out
        assert any(e.type == "expenses_deleted" and e.data["count"] == 2 for e in events)
        remaining = db.query(models.Transaction).filter_by(user_id=u.id).all()
        # August Food + July Transport survive; both July Food rows are gone.
        assert len(remaining) == 2
        assert {int(t.amount) for t in remaining} == {900, 300}
    finally:
        db.close()


def test_delete_expenses_scoped_to_single_day():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            tools.add_expense.invoke({"amount": 500, "category": "Food", "date": "2026-07-03"})
            tools.add_expense.invoke({"amount": 700, "category": "Food", "date": "2026-07-20"})
            out = tools.delete_expenses.invoke({"category": "Food", "date": "2026-07-03"})

        assert "2026-07-03" in out
        remaining = db.query(models.Transaction).filter_by(user_id=u.id).all()
        assert [int(t.amount) for t in remaining] == [700]
    finally:
        db.close()


def test_delete_expenses_unknown_category_is_a_noop():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            out = tools.delete_expenses.invoke({"category": "Nope", "month": "2026-07"})
        assert "no category" in out.lower()
    finally:
        db.close()


def test_investments_record_and_query():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            tools.add_investment.invoke(
                {"amount": 10000, "month": "2026-07", "category": "mutual funds"}
            )
            out = tools.query_investments.invoke({"month": "2026-07"})
        assert "10,000" in out
    finally:
        db.close()
