def _category_id(client, name: str) -> int:
    cats = client.get("/categories").json()
    return next(c["id"] for c in cats if c["name"] == name)


def test_spending_by_category(client):
    food = _category_id(client, "Food")
    transport = _category_id(client, "Transport")
    client.post("/transactions", json={"amount": 500, "category_id": food, "occurred_on": "2026-07-01"})
    client.post("/transactions", json={"amount": 300, "category_id": food, "occurred_on": "2026-07-10"})
    client.post("/transactions", json={"amount": 200, "category_id": transport, "occurred_on": "2026-07-11"})

    rows = client.get("/dashboard/spending", params={"month": "2026-07"}).json()
    totals = {r["category_name"]: r["total"] for r in rows}
    assert totals["Food"] == 800
    assert totals["Transport"] == 200
    # Sorted by total desc.
    assert rows[0]["category_name"] == "Food"


def test_monthly_investments(client):
    client.post("/investments", json={"amount": 10000, "month": "2026-06", "category": "mutual funds"})
    client.post("/investments", json={"amount": 5000, "month": "2026-07", "category": "stocks"})
    client.post("/investments", json={"amount": 2000, "month": "2026-07", "category": "gold"})

    rows = client.get("/dashboard/investments", params={"year": 2026}).json()
    by_month = {r["month"]: r["total"] for r in rows}
    assert by_month["2026-06"] == 10000
    assert by_month["2026-07"] == 7000


def test_month_validation_rejects_bad_format(client):
    resp = client.get("/dashboard/spending", params={"month": "2026/07"})
    assert resp.status_code == 400
