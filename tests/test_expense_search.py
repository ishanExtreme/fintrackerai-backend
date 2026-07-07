"""Unit tests for the search_expenses agent tool."""

import datetime as dt

from app import models
from app.db import SessionLocal
from app.seed import seed_default_categories
from app.services.agent import tools
from app.services.agent.runtime import request_scope

JULY = dt.date(2026, 7, 3)


def _mk_user(db):
    u = models.User(firebase_uid="search-user", email="s@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    seed_default_categories(db, u.id)
    return u


def test_search_expenses_by_date_range():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            tools.add_expense.invoke({"amount": 500, "category": "Food", "date": "2026-07-01"})
            tools.add_expense.invoke({"amount": 300, "category": "Food", "date": "2026-07-02"})
            tools.add_expense.invoke({"amount": 200, "category": "Transport", "date": "2026-07-03"})
            out = tools.search_expenses.invoke({
                "from_date": "2026-07-01",
                "to_date": "2026-07-03",
            })
        assert "500" in out
        assert "300" in out
        assert "200" in out
        assert "3 expenses" in out.lower() or "3 expense" in out.lower()
    finally:
        db.close()


def test_search_expenses_by_category_and_date():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            tools.add_expense.invoke({"amount": 500, "category": "Food", "date": "2026-07-01"})
            tools.add_expense.invoke({"amount": 300, "category": "Food", "date": "2026-07-02"})
            tools.add_expense.invoke({"amount": 200, "category": "Transport", "date": "2026-07-03"})
            out = tools.search_expenses.invoke({
                "category": "Food",
                "from_date": "2026-07-01",
                "to_date": "2026-07-03",
            })
        assert "500" in out
        assert "300" in out
        assert "200" not in out  # Transport should not match
        assert "2 expenses" in out.lower() or "2 expense" in out.lower()
    finally:
        db.close()


def test_search_expenses_by_description_keyword():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            # Create transactions directly with description set (add_expense uses 'note' not 'description')
            txn1 = models.Transaction(
                user_id=u.id,
                amount=500,
                currency="INR",
                occurred_on=dt.date(2026, 7, 1),
                description="ordered biryani from XYZ restaurant",
                source="chat",
            )
            txn2 = models.Transaction(
                user_id=u.id,
                amount=300,
                currency="INR",
                occurred_on=dt.date(2026, 7, 2),
                description="ordered pizza from Domino's",
                source="chat",
            )
            db.add(txn1)
            db.add(txn2)
            db.commit()
            out = tools.search_expenses.invoke({
                "from_date": "2026-07-01",
                "to_date": "2026-07-03",
                "description": "biryani",
            })
        assert "500" in out
        assert "300" not in out  # pizza doesn't match biryani
        assert "1 expense" in out.lower()
    finally:
        db.close()


def test_search_expenses_by_subtitle_keyword():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            # Create a transaction with subtitle by adding a note (subtitle is set separately)
            # Since add_expense doesn't set subtitle, we create directly
            txn = models.Transaction(
                user_id=u.id,
                amount=500,
                currency="INR",
                occurred_on=dt.date(2026, 7, 1),
                subtitle="lunch order",
                description="biryani meal",
                source="chat",
            )
            db.add(txn)
            db.commit()
            out = tools.search_expenses.invoke({
                "from_date": "2026-07-01",
                "to_date": "2026-07-03",
                "description": "lunch",
            })
        assert "500" in out
        assert "1 expense" in out.lower()
    finally:
        db.close()


def test_search_expenses_no_results():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            out = tools.search_expenses.invoke({
                "category": "NonExistent",
                "from_date": "2026-07-01",
                "to_date": "2026-07-03",
            })
        assert "no expense" in out.lower()
    finally:
        db.close()


def test_search_expenses_date_range_exceeds_31_days():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            out = tools.search_expenses.invoke({
                "from_date": "2026-01-01",
                "to_date": "2026-07-01",
            })
        assert "31 days" in out or "exceeds" in out.lower()
    finally:
        db.close()


def test_search_expenses_defaults_to_current_month():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            tools.add_expense.invoke({"amount": 500, "category": "Food", "date": "2026-07-03"})
            tools.add_expense.invoke({"amount": 200, "category": "Food", "date": "2026-06-15"})
            # No dates provided → should default to current month (July)
            out = tools.search_expenses.invoke({})
        assert "500" in out
        assert "200" not in out  # June expense should not appear
    finally:
        db.close()


def test_search_expenses_includes_subcategories():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            tools.add_expense.invoke({
                "amount": 1200,
                "category": "Movie tickets",
                "parent_category": "Personal",
                "date": "2026-07-05",
            })
            out = tools.search_expenses.invoke({
                "category": "Personal",
                "from_date": "2026-07-01",
                "to_date": "2026-07-31",
            })
        assert "1,200" in out  # formatted with comma
        assert "1 expense" in out.lower()
    finally:
        db.close()


def test_search_expenses_total_amount():
    db = SessionLocal()
    try:
        u = _mk_user(db)
        with request_scope(db=db, user_id=u.id, llm_key=None, today=JULY):
            tools.add_expense.invoke({"amount": 500, "category": "Food", "date": "2026-07-01"})
            tools.add_expense.invoke({"amount": 300, "category": "Food", "date": "2026-07-02"})
            out = tools.search_expenses.invoke({
                "from_date": "2026-07-01",
                "to_date": "2026-07-03",
            })
        assert "800" in out  # 500 + 300 = 800
    finally:
        db.close()