def _category_id(client, name: str) -> int:
    cats = client.get("/categories").json()
    return next(c["id"] for c in cats if c["name"] == name)


def test_create_transaction_and_list_by_month(client):
    food = _category_id(client, "Food")
    resp = client.post(
        "/transactions",
        json={
            "amount": 500,
            "category_id": food,
            "occurred_on": "2026-07-01",
            "note": "biryani",
            "source": "chat",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["amount"] == 500

    listed = client.get("/transactions", params={"month": "2026-07"}).json()
    assert len(listed) == 1
    assert listed[0]["note"] == "biryani"

    empty = client.get("/transactions", params={"month": "2026-06"}).json()
    assert empty == []


def test_budget_upsert_and_status_rolls_up_subcategories(client):
    personal = _category_id(client, "Personal")
    # Sub-category under Personal.
    sub = client.post(
        "/categories", json={"name": "Movie tickets", "parent_id": personal}
    ).json()

    # Budget on the parent.
    client.put(
        "/budgets",
        json={"category_id": personal, "month": "2026-07", "limit_amount": 5000},
    )

    # Spend recorded on the sub-category should count against the parent budget.
    client.post(
        "/transactions",
        json={"amount": 1200, "category_id": sub["id"], "occurred_on": "2026-07-05"},
    )

    status = client.get("/dashboard/budget-status", params={"month": "2026-07"}).json()
    row = next(r for r in status if r["category_id"] == personal)
    assert row["limit_amount"] == 5000
    assert row["spent"] == 1200
    assert row["remaining"] == 3800


def test_sms_ingest_dedupes_and_skips_credits(client):
    payload = {
        "amount": 250,
        "direction": "debit",
        "raw_hash": "abc123",
        "merchant": "Swiggy",
        "occurred_on": "2026-07-02",
        "account_masked": "XX1234",
    }
    first = client.post("/transactions/ingest", json=payload).json()
    assert first["status"] == "created"
    assert first["transaction"]["source"] == "sms"

    dup = client.post("/transactions/ingest", json=payload).json()
    assert dup["status"] == "duplicate"

    credit = client.post(
        "/transactions/ingest",
        json={"amount": 999, "direction": "credit", "raw_hash": "credit-1"},
    ).json()
    assert credit["status"] == "skipped"

    txns = client.get("/transactions", params={"month": "2026-07"}).json()
    assert len(txns) == 1  # only the single debit
