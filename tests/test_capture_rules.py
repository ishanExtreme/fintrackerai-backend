"""Tests for the "remember" / capture-rules feature: payee + location rules,
precedence, retroactive re-apply, and CRUD."""

import app.services.sms_capture as sms_capture
from app.services.sms_capture import SmsExpense


def _cat(client, name: str) -> int:
    cats = client.get("/categories").json()
    return next(c["id"] for c in cats if c["name"] == name)


def _set_sms_key(client):
    client.put("/settings/sms-llm-key", json={"api_key": "k", "provider": "google_genai"})


def _patch(monkeypatch, **fields):
    defaults = dict(
        is_expense=True, amount=120.0, direction="debit", category="Food",
        parent_category=None, counterparty="randomname@okhdfc",
        subtitle="UPI - random", description=None, note=None,
        occurred_on="2026-07-15", confidence=0.6,
    )
    defaults.update(fields)
    result = SmsExpense(**defaults)

    class _S:
        def invoke(self, _):
            return result

    class _M:
        def with_structured_output(self, _):
            return _S()

    monkeypatch.setattr(sms_capture, "get_model", lambda model=None: _M())


def _capture(client, raw_hash, **extra):
    body = {"sms_text": "Rs.120 debited to randomname@okhdfc", "raw_hash": raw_hash}
    body.update(extra)
    return client.post("/transactions/capture", json=body).json()


# ------------------------------ payee rule ------------------------------ #
def test_payee_rule_precorrects_future_capture(client, monkeypatch):
    _set_sms_key(client)
    transport = _cat(client, "Transport")
    r = client.post("/capture-rules", json={
        "kind": "payee", "match_value": "randomname@okhdfc",
        "category_id": transport, "subtitle": "Office cafeteria",
    })
    assert r.status_code == 201, r.text
    assert r.json()["applied"] == 0  # nothing to backfill yet

    _patch(monkeypatch)
    txn = _capture(client, "pay-1")["transaction"]
    assert txn["category_id"] == transport   # payee override beat LLM's "Food"
    assert txn["subtitle"] == "Office cafeteria"
    assert txn["reviewed"] is False           # still shows in Auto
    assert txn["counterparty"] == "randomname@okhdfc"


def test_payee_rule_reapplies_to_existing_unreviewed(client, monkeypatch):
    _set_sms_key(client)
    _patch(monkeypatch)
    # Capture first — lands as Food / "UPI - random".
    first = _capture(client, "pay-2")["transaction"]
    assert first["subtitle"] == "UPI - random"

    transport = _cat(client, "Transport")
    r = client.post("/capture-rules", json={
        "kind": "payee", "match_value": "randomname@okhdfc",
        "category_id": transport, "subtitle": "Office cafeteria",
    }).json()
    assert r["applied"] == 1  # backfilled the existing capture

    listed = client.get(
        "/transactions", params={"month": "2026-07", "source": "sms"}
    ).json()
    assert listed[0]["category_id"] == transport
    assert listed[0]["subtitle"] == "Office cafeteria"


# ---------------------------- location rule ----------------------------- #
def test_location_rule_sets_place_label_and_fallback_category(client, monkeypatch):
    _set_sms_key(client)
    food = _cat(client, "Food")
    client.post("/capture-rules", json={
        "kind": "location", "lat": 12.9716, "lng": 77.5946, "radius_m": 300,
        "location_name": "Office", "category_id": food,
    })
    # LLM couldn't categorise (Uncategorized) → location fallback applies.
    _patch(monkeypatch, category="Uncategorized", counterparty="shop@ok")
    txn = _capture(client, "loc-1", lat=12.9717, lng=77.5947)["transaction"]
    assert txn["location_label"] == "Office"
    assert txn["category_id"] == food  # fallback used since LLM gave none


def test_location_rule_out_of_radius_does_not_match(client, monkeypatch):
    _set_sms_key(client)
    food = _cat(client, "Food")
    client.post("/capture-rules", json={
        "kind": "location", "lat": 12.9716, "lng": 77.5946, "radius_m": 150,
        "location_name": "Office", "category_id": food,
    })
    _patch(monkeypatch, category="Uncategorized", counterparty="shop@ok")
    # ~1.5 km away.
    txn = _capture(client, "loc-2", lat=12.9850, lng=77.5946)["transaction"]
    assert txn["location_label"] is None
    assert txn["category_id"] is None


def test_payee_beats_location_for_category(client, monkeypatch):
    _set_sms_key(client)
    food = _cat(client, "Food")
    transport = _cat(client, "Transport")
    client.post("/capture-rules", json={
        "kind": "location", "lat": 12.9716, "lng": 77.5946, "radius_m": 300,
        "location_name": "Office", "category_id": food,
    })
    client.post("/capture-rules", json={
        "kind": "payee", "match_value": "randomname@okhdfc", "category_id": transport,
    })
    _patch(monkeypatch, category="Uncategorized")
    txn = _capture(client, "prec-1", lat=12.9717, lng=77.5947)["transaction"]
    assert txn["location_label"] == "Office"       # from location rule
    assert txn["category_id"] == transport         # payee wins over location


# -------------------------------- CRUD ---------------------------------- #
def test_rule_crud_and_validation(client):
    assert client.get("/capture-rules").json() == []

    bad = client.post("/capture-rules", json={"kind": "payee"})
    assert bad.status_code == 400  # payee needs match_value
    bad2 = client.post("/capture-rules", json={"kind": "location", "location_name": "X"})
    assert bad2.status_code == 400  # location needs lat/lng

    created = client.post("/capture-rules", json={
        "kind": "payee", "match_value": "x@ok", "subtitle": "Lunch",
    }).json()["rule"]
    assert created["kind"] == "payee"

    listed = client.get("/capture-rules").json()
    assert len(listed) == 1

    assert client.delete(f"/capture-rules/{created['id']}").status_code == 204
    assert client.get("/capture-rules").json() == []
