"""Agent HTTP API — end-to-end via FastAPI TestClient."""

from __future__ import annotations

from app.seed import seed_data


def _seeded(session):
    seed_data(session)
    session.commit()


# ---- /agent/search ---------------------------------------------------------


def test_agent_search(api):
    client, session = api
    _seeded(session)
    r = client.post(
        "/agent/search",
        json={"merchant_id": "mer_priya_coffee", "category": "coffee"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["merchant_id"] == "mer_priya_coffee"
    names = {p["name"] for p in body["products"]}
    assert names == {"Classic Coffee", "Premium Coffee"}


def test_agent_search_query_partial_match(api):
    client, session = api
    _seeded(session)
    r = client.post(
        "/agent/search",
        json={"merchant_id": "mer_priya_coffee", "query": "espresso"},
    )
    assert r.status_code == 200
    names = {p["name"] for p in r.json()["products"]}
    assert "Espresso Beans" in names


# ---- /agent/build-cart -----------------------------------------------------


def test_agent_build_cart_allows(api):
    client, session = api
    _seeded(session)
    r = client.post(
        "/agent/build-cart",
        json={
            "customer_id": "cust_priya_regular",
            "items": [{"catalog_item_id": "cat_classic_coffee", "quantity": 1}],
            "idempotency_key": "api_build_1",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["warden"]["decision"] == "ALLOW"
    assert body["quote"]["total"] == "699.00"
    assert body["cart_id"].startswith("cart_")


def test_agent_build_cart_blocks_over_cap(api):
    client, session = api
    _seeded(session)
    r = client.post(
        "/agent/build-cart",
        json={
            "customer_id": "cust_priya_regular",
            "items": [
                {"catalog_item_id": "cat_coffee_machine", "quantity": 1},  # ₹3499
            ],
            "idempotency_key": "api_build_over",
        },
    )
    body = r.json()
    assert body["warden"]["decision"] == "BLOCK"
    # Either CAP_EXCEEDED (amount check) or OUT_OF_SCOPE_CATEGORY (appliance);
    # the coffee_machine is category="appliance" and mandate A only allows
    # coffee — so we expect OUT_OF_SCOPE first per the check order.
    assert body["warden"]["reason_code"] == "OUT_OF_SCOPE_CATEGORY"


def test_agent_build_cart_missing_customer_mandate(api):
    client, session = api
    _seeded(session)
    r = client.post(
        "/agent/build-cart",
        json={
            "customer_id": "cust_ghost",
            "items": [{"catalog_item_id": "cat_classic_coffee", "quantity": 1}],
            "idempotency_key": "api_build_ghost",
        },
    )
    assert r.status_code == 404


# ---- /agent/purchase-intent -------------------------------------------------


def test_agent_purchase_intent_full_flow(api):
    """The showcase E2E: 'Restock my coffee' -> ALLOW with a warden.action_id."""
    client, session = api
    _seeded(session)

    r = client.post(
        "/agent/purchase-intent",
        json={
            "natural_language": "Restock my coffee this month. Spend no more than ₹2000.",
            "customer_id": "cust_priya_regular",
            "idempotency_key": "api_intent_1",
        },
    )
    assert r.status_code == 200
    body = r.json()

    # Parsed intent has category and confidence.
    assert body["parsed_intent"]["desired_category"] == "coffee"
    assert body["parsed_intent"]["confidence"] >= 0.7

    # Mandate resolved to A.
    assert body["mandate"]["id"] == "man_A_regular_2k"

    # Cart persisted.
    assert body["cart_id"].startswith("cart_")

    # Warden ALLOWed.
    assert body["warden"]["decision"] == "ALLOW"
    assert body["warden"]["reason_code"] == "OK"
    assert body["warden"]["action_id"].startswith("act_")

    # Agent verdict mirrors Warden.
    assert body["agent_verdict"] == "ALLOW"
    assert body["explanation"]


def test_agent_purchase_intent_no_mandate(api):
    client, session = api
    _seeded(session)
    r = client.post(
        "/agent/purchase-intent",
        json={
            "natural_language": "Restock my coffee.",
            "customer_id": "cust_nobody",
            "idempotency_key": "api_intent_nomandate",
        },
    )
    assert r.status_code == 404


def test_agent_purchase_intent_is_idempotent(api):
    client, session = api
    _seeded(session)

    r1 = client.post(
        "/agent/purchase-intent",
        json={
            "natural_language": "Restock my coffee. Spend up to ₹1000.",
            "customer_id": "cust_priya_regular",
            "idempotency_key": "api_intent_dup",
        },
    ).json()
    r2 = client.post(
        "/agent/purchase-intent",
        json={
            "natural_language": "Restock my coffee. Spend up to ₹1000.",
            "customer_id": "cust_priya_regular",
            "idempotency_key": "api_intent_dup",
        },
    ).json()

    # Both agents run and each builds a cart, but Warden returns the same
    # action_id and marks the second one as a duplicate.
    assert r2["warden"]["action_id"] == r1["warden"]["action_id"]
    assert r2["warden"]["duplicate"] is True


# ---- /agent/explain --------------------------------------------------------


def test_agent_explain_by_action_id(api):
    client, session = api
    _seeded(session)

    intent = client.post(
        "/agent/purchase-intent",
        json={
            "natural_language": "Restock my coffee.",
            "customer_id": "cust_priya_regular",
            "idempotency_key": "api_explain_1",
        },
    ).json()

    r = client.post(
        "/agent/explain",
        json={"action_id": intent["warden"]["action_id"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action_id"] == intent["warden"]["action_id"]
    assert body["natural_language"]


def test_agent_explain_inline_fields(api):
    client, session = api
    _seeded(session)

    r = client.post(
        "/agent/explain",
        json={
            "result": "BLOCK",
            "reason_code": "CAP_EXCEEDED",
            "warden_explanation": "₹3000 > remaining ₹2000",
        },
    )
    assert r.status_code == 200
    assert r.json()["reason_code"] == "CAP_EXCEEDED"


def test_agent_explain_requires_action_or_fields(api):
    client, session = api
    _seeded(session)
    r = client.post("/agent/explain", json={})
    assert r.status_code == 400


def test_agent_explain_missing_action_id(api):
    client, session = api
    _seeded(session)
    r = client.post("/agent/explain", json={"action_id": "act_missing"})
    assert r.status_code == 404
