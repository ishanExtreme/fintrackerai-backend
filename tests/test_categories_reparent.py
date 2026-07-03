"""Reparenting categories via PATCH — backs the app's drag-and-drop."""


def _mk(client, name, parent_id=None):
    body = {"name": name}
    if parent_id is not None:
        body["parent_id"] = parent_id
    r = client.post("/categories", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_move_category_under_another_parent(client):
    a = _mk(client, "Personal")
    b = _mk(client, "Work")
    child = _mk(client, "Books", parent_id=a)

    r = client.patch(f"/categories/{child}", json={"parent_id": b})
    assert r.status_code == 200
    assert r.json()["parent_id"] == b


def test_detach_subcategory_to_top_level(client):
    a = _mk(client, "Personal")
    child = _mk(client, "Books", parent_id=a)

    r = client.patch(f"/categories/{child}", json={"parent_id": None})
    assert r.status_code == 200
    assert r.json()["parent_id"] is None


def test_cannot_move_category_under_itself(client):
    a = _mk(client, "Personal")
    assert client.patch(f"/categories/{a}", json={"parent_id": a}).status_code == 400


def test_cannot_move_category_under_its_own_descendant(client):
    a = _mk(client, "Personal")
    child = _mk(client, "Books", parent_id=a)
    grandchild = _mk(client, "Fiction", parent_id=child)

    # Moving A under its grandchild would create a cycle.
    assert client.patch(f"/categories/{a}", json={"parent_id": grandchild}).status_code == 400
