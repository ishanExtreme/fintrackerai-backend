"""Bulk-delete endpoint — the app's "reset expenses" action."""


def _mk_txn(client, amount, occurred_on, category_id=None):
    body = {"amount": amount, "currency": "INR", "occurred_on": occurred_on, "source": "manual"}
    if category_id is not None:
        body["category_id"] = category_id
    r = client.post("/transactions", json=body)
    assert r.status_code == 201, r.text


def _mk_cat(client, name, parent_id=None):
    body = {"name": name}
    if parent_id is not None:
        body["parent_id"] = parent_id
    r = client.post("/categories", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_delete_by_month_only_removes_that_month(client):
    _mk_txn(client, 100, "2026-07-03")
    _mk_txn(client, 200, "2026-07-28")
    _mk_txn(client, 300, "2026-08-01")

    r = client.delete("/transactions", params={"month": "2026-07"})
    assert r.status_code == 200
    assert r.json()["deleted"] == 2

    left = client.get("/transactions").json()
    assert [int(t["amount"]) for t in left] == [300]


def test_delete_all_wipes_everything(client):
    _mk_txn(client, 100, "2026-07-03")
    _mk_txn(client, 300, "2026-08-01")

    r = client.delete("/transactions", params={"all": True})
    assert r.status_code == 200
    assert r.json()["deleted"] == 2
    assert client.get("/transactions").json() == []


def test_delete_requires_exactly_one_scope(client):
    # Neither → 400.
    assert client.delete("/transactions").status_code == 400
    # Both → 400.
    assert client.delete(
        "/transactions", params={"month": "2026-07", "all": True}
    ).status_code == 400


def test_delete_rejects_bad_month(client):
    assert client.delete("/transactions", params={"month": "2026-13"}).status_code == 400


def test_delete_month_scoped_to_category_includes_subcategories(client):
    food = _mk_cat(client, "Food")
    dining = _mk_cat(client, "Dining", parent_id=food)
    transport = _mk_cat(client, "Transport")
    _mk_txn(client, 100, "2026-07-03", category_id=food)
    _mk_txn(client, 200, "2026-07-10", category_id=dining)  # sub-category of Food
    _mk_txn(client, 300, "2026-07-12", category_id=transport)
    _mk_txn(client, 400, "2026-08-01", category_id=food)  # different month

    r = client.delete("/transactions", params={"month": "2026-07", "category_id": food})
    assert r.status_code == 200
    assert r.json()["deleted"] == 2  # Food + its sub-category Dining, July only

    left = {int(t["amount"]) for t in client.get("/transactions").json()}
    assert left == {300, 400}


def test_delete_month_scoped_to_uncategorized(client):
    food = _mk_cat(client, "Food")
    _mk_txn(client, 100, "2026-07-03")  # uncategorized
    _mk_txn(client, 200, "2026-07-05", category_id=food)

    r = client.delete("/transactions", params={"month": "2026-07", "uncategorized": True})
    assert r.status_code == 200
    assert r.json()["deleted"] == 1

    left = [int(t["amount"]) for t in client.get("/transactions").json()]
    assert left == [200]


def test_delete_category_and_uncategorized_are_mutually_exclusive(client):
    food = _mk_cat(client, "Food")
    assert client.delete(
        "/transactions",
        params={"month": "2026-07", "category_id": food, "uncategorized": True},
    ).status_code == 400


def test_delete_all_rejects_extra_filters(client):
    assert client.delete(
        "/transactions", params={"all": True, "uncategorized": True}
    ).status_code == 400


def test_delete_unknown_category_rejected(client):
    assert client.delete(
        "/transactions", params={"month": "2026-07", "category_id": 999999}
    ).status_code == 400
