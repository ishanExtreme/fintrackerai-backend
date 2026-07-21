"""Tests for Phase 5 SMS auto-capture: /transactions/capture, /review-batch,
and the dedicated SMS LLM key endpoints.

The LLM structured-output call is faked so no network/key is needed; we assert
the endpoint wiring (dedupe, skip, category resolution, GPS, review flow).
"""

import app.services.sms_capture as sms_capture
from app.services.sms_capture import SmsExpense


def _category_id(client, name: str) -> int:
    cats = client.get("/categories").json()
    return next(c["id"] for c in cats if c["name"] == name)


def _patch_model(monkeypatch, **fields):
    """Make sms_capture.get_model() return a fake model yielding an SmsExpense."""
    defaults = dict(
        is_expense=True,
        amount=500.0,
        direction="debit",
        category="Food",
        parent_category=None,
        counterparty="randomname@okhdfc",
        subtitle="UPI - Swiggy",
        description=None,
        note=None,
        occurred_on="2026-07-15",
        confidence=0.9,
    )
    defaults.update(fields)
    result = SmsExpense(**defaults)

    class _FakeStructured:
        def invoke(self, _prompt):
            return result

    class _FakeModel:
        def with_structured_output(self, _schema):
            return _FakeStructured()

    monkeypatch.setattr(sms_capture, "get_model", lambda model=None: _FakeModel())
    return result


def _set_sms_key(client, model=None):
    body = {"api_key": "fake-sms-key", "provider": "google_genai"}
    if model:
        body["model"] = model
    return client.put("/settings/sms-llm-key", json=body)


# --------------------------------- capture --------------------------------- #
def test_capture_debit_creates_reviewable_sms_transaction(client, monkeypatch):
    _patch_model(monkeypatch)
    _set_sms_key(client)

    resp = client.post(
        "/transactions/capture",
        json={
            "sms_text": "Rs.500 debited via UPI to Swiggy",
            "sender": "HDFCBK",
            "raw_hash": "hash-1",
            "lat": 12.97,
            "lng": 77.59,
            "place_label": "Toit, Indiranagar",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "created"
    txn = body["transaction"]
    assert txn["source"] == "sms"
    assert txn["reviewed"] is False
    assert txn["amount"] == 500.0
    assert txn["confidence"] == 0.9
    assert txn["category_id"] == _category_id(client, "Food")
    assert txn["lat"] == 12.97 and txn["lng"] == 77.59
    assert txn["location_label"] == "Toit, Indiranagar"

    listed = client.get(
        "/transactions",
        params={"month": "2026-07", "source": "sms", "reviewed": False},
    ).json()
    assert len(listed) == 1
    assert listed[0]["id"] == txn["id"]


def test_capture_duplicate_hash_is_deduped(client, monkeypatch):
    _patch_model(monkeypatch)
    _set_sms_key(client)
    payload = {"sms_text": "Rs.500 debited", "raw_hash": "dupe-hash"}

    first = client.post("/transactions/capture", json=payload).json()
    assert first["status"] == "created"
    second = client.post("/transactions/capture", json=payload).json()
    assert second["status"] == "duplicate"

    listed = client.get(
        "/transactions", params={"month": "2026-07", "source": "sms"}
    ).json()
    assert len(listed) == 1


def test_capture_non_expense_is_skipped(client, monkeypatch):
    _patch_model(monkeypatch, is_expense=False)
    _set_sms_key(client)
    resp = client.post(
        "/transactions/capture",
        json={"sms_text": "Your OTP is 123456", "raw_hash": "otp-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"
    listed = client.get(
        "/transactions", params={"month": "2026-07", "source": "sms"}
    ).json()
    assert listed == []


def test_capture_uncategorized_stores_null_category(client, monkeypatch):
    _patch_model(monkeypatch, category="Uncategorized")
    _set_sms_key(client)
    resp = client.post(
        "/transactions/capture",
        json={"sms_text": "Rs.99 debited somewhere", "raw_hash": "uncat-1"},
    )
    txn = resp.json()["transaction"]
    assert txn["category_id"] is None


def test_capture_without_gps_ok(client, monkeypatch):
    _patch_model(monkeypatch)
    _set_sms_key(client)
    resp = client.post(
        "/transactions/capture",
        json={"sms_text": "Rs.500 debited", "raw_hash": "nogps-1"},
    )
    txn = resp.json()["transaction"]
    assert txn["lat"] is None and txn["lng"] is None
    assert txn["location_label"] is None


def test_capture_without_any_key_is_skipped(client, monkeypatch):
    # No SMS key, no chat key, no shared key configured → skip (don't 500).
    # The test env's .env may carry a shared key, so force the no-key path.
    import app.routers.transactions as txn_router

    _patch_model(monkeypatch)
    monkeypatch.setattr(txn_router, "resolve_sms_llm_key", lambda db, user: None)
    resp = client.post(
        "/transactions/capture",
        json={"sms_text": "Rs.500 debited", "raw_hash": "nokey-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


# ------------------------------- review-batch ------------------------------ #
def _capture(client, raw_hash):
    return client.post(
        "/transactions/capture",
        json={"sms_text": "Rs.500 debited", "raw_hash": raw_hash},
    ).json()["transaction"]


def test_review_batch_by_ids(client, monkeypatch):
    _patch_model(monkeypatch)
    _set_sms_key(client)
    t1 = _capture(client, "r-1")
    t2 = _capture(client, "r-2")

    resp = client.post("/transactions/review-batch", json={"ids": [t1["id"], t2["id"]]})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 2

    remaining = client.get(
        "/transactions",
        params={"month": "2026-07", "source": "sms", "reviewed": False},
    ).json()
    assert remaining == []


def test_review_batch_by_month(client, monkeypatch):
    _patch_model(monkeypatch)
    _set_sms_key(client)
    _capture(client, "m-1")
    _capture(client, "m-2")

    resp = client.post("/transactions/review-batch", json={"month": "2026-07"})
    assert resp.json()["updated"] == 2
    reviewed = client.get(
        "/transactions",
        params={"month": "2026-07", "source": "sms", "reviewed": True},
    ).json()
    assert len(reviewed) == 2


def test_review_batch_requires_ids_or_month(client):
    resp = client.post("/transactions/review-batch", json={})
    assert resp.status_code == 400


# ----------------------------- SMS LLM key API ----------------------------- #
def test_sms_llm_key_set_status_delete(client):
    status = client.get("/settings/sms-llm-key").json()
    assert status["configured"] is False

    put = client.put(
        "/settings/sms-llm-key",
        json={"api_key": "k", "provider": "google_genai", "model": "google_genai:gemini-flash-lite"},
    ).json()
    assert put["configured"] is True
    assert put["model"] == "google_genai:gemini-flash-lite"

    got = client.get("/settings/sms-llm-key").json()
    assert got["configured"] is True
    assert got["using"] == "user"
    assert got["model"] == "google_genai:gemini-flash-lite"

    assert client.delete("/settings/sms-llm-key").status_code == 204
    assert client.get("/settings/sms-llm-key").json()["configured"] is False


def test_sms_key_is_independent_from_chat_key(client):
    # Setting only the chat key leaves the SMS key unconfigured but usable.
    client.put("/settings/llm-key", json={"api_key": "chatkey", "provider": "google_genai"})
    sms = client.get("/settings/sms-llm-key").json()
    assert sms["configured"] is False
    assert sms["using"] == "chat"
