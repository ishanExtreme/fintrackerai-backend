"""Bulk-delete endpoint — the app's "reset expenses" action."""


def _mk_txn(client, amount, occurred_on):
    r = client.post(
        "/transactions",
        json={"amount": amount, "currency": "INR", "occurred_on": occurred_on, "source": "manual"},
    )
    assert r.status_code == 201, r.text


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
