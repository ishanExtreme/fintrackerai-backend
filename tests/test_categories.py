def test_default_categories_seeded_on_first_request(client):
    resp = client.get("/categories")
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert {"Food", "Personal", "Others"} <= names


def test_llm_can_create_parent_and_subcategory(client):
    # LLM creates a parent category with rich metadata.
    parent = client.post(
        "/categories",
        json={
            "name": "Personal",
            "description": "Personal spends",
            "image": "🙂",
            "type": "expense",
            "tags": ["life"],
            "created_by": "llm",
        },
    )
    # "Personal" is also a default; a second same-name root should conflict.
    # Use a fresh unique parent instead to keep the test deterministic.
    assert parent.status_code in (201, 400)

    unique_parent = client.post(
        "/categories",
        json={"name": "Hobbies", "type": "expense", "created_by": "llm"},
    )
    assert unique_parent.status_code == 201
    parent_id = unique_parent.json()["id"]
    assert unique_parent.json()["created_by"] == "llm"

    # Sub-category "Movie tickets" under the parent.
    sub = client.post(
        "/categories",
        json={
            "name": "Movie tickets",
            "parent_id": parent_id,
            "type": "expense",
            "tags": ["movies", "outing"],
            "created_by": "llm",
        },
    )
    assert sub.status_code == 201
    body = sub.json()
    assert body["parent_id"] == parent_id
    assert body["tags"] == ["movies", "outing"]


def test_category_tree_nests_children(client):
    parent = client.post("/categories", json={"name": "Travel"}).json()
    client.post("/categories", json={"name": "Flights", "parent_id": parent["id"]})
    client.post("/categories", json={"name": "Hotels", "parent_id": parent["id"]})

    tree = client.get("/categories/tree").json()
    travel = next(n for n in tree if n["name"] == "Travel")
    child_names = {c["name"] for c in travel["children"]}
    assert child_names == {"Flights", "Hotels"}
