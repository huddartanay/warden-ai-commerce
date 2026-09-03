"""HTTP-level tests for the Warden API."""

from __future__ import annotations

from decimal import Decimal

from app.seed import seed_data


def _seeded(session):
    seed_data(session)
    session.commit()


def _payload(**overrides) -> dict:
    body = {
        "mandate_id": "man_A_regular_2k",
        "customer_id": "cust_priya_regular",
        "merchant_id": "mer_priya_coffee",
        "cart_id": "cart_api_1",
        "amount": "1499.00",
        "currency": "INR",
        "category": "coffee",
        "quoted_price": "1499.00",
        "current_price": "1499.00",
        "idempotency_key": "idem_api_1",
    }
    body.update(overrides)
    return body


def test_post_evaluate_allow(api):
    client, session = api
    _seeded(session)

    r = client.post("/warden/evaluate", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "ALLOW"
    assert body["reason_code"] == "OK"
    assert body["duplicate"] is False
    assert isinstance(body["checks_performed"], list) and body["checks_performed"]
    assert body["action_id"].startswith("act_")


def test_post_evaluate_block_cap_exceeded(api):
    client, session = api
    _seeded(session)

    r = client.post("/warden/evaluate", json=_payload(amount="3499.00"))
    body = r.json()
    assert r.status_code == 200
    assert body["decision"] == "BLOCK"
    assert body["reason_code"] == "CAP_EXCEEDED"
    assert "₹3,499.00" in body["explanation"]


def test_post_evaluate_block_category_out_of_scope(api):
    client, session = api
    _seeded(session)

    r = client.post("/warden/evaluate", json=_payload(category="appliance"))
    body = r.json()
    assert body["decision"] == "BLOCK"
    assert body["reason_code"] == "OUT_OF_SCOPE_CATEGORY"


def test_post_evaluate_step_up(api):
    client, session = api
    _seeded(session)

    r = client.post(
        "/warden/evaluate",
        json=_payload(
            mandate_id="man_B_bulk_5k",
            customer_id="cust_bulk_buyer",
            amount="2500.00",
            quoted_price="2500.00",
            current_price="2500.00",
            idempotency_key="idem_api_stepup",
        ),
    )
    body = r.json()
    assert body["decision"] == "STEP_UP"
    assert body["reason_code"] == "APPROVAL_REQUIRED"


def test_post_evaluate_is_idempotent(api):
    client, session = api
    _seeded(session)

    r1 = client.post("/warden/evaluate", json=_payload(idempotency_key="idem_api_dup")).json()
    r2 = client.post("/warden/evaluate", json=_payload(idempotency_key="idem_api_dup")).json()

    assert r1["duplicate"] is False
    assert r2["duplicate"] is True
    assert r2["action_id"] == r1["action_id"]
    assert r2["decision"] == r1["decision"]


def test_post_evaluate_block_price_drift(api):
    client, session = api
    _seeded(session)

    r = client.post(
        "/warden/evaluate",
        json=_payload(quoted_price="1499.00", current_price="1600.00"),
    )
    body = r.json()
    assert body["decision"] == "BLOCK"
    assert body["reason_code"] == "PRICE_DRIFT"


def test_post_evaluate_block_invalid_customer(api):
    client, session = api
    _seeded(session)

    r = client.post(
        "/warden/evaluate", json=_payload(customer_id="cust_someone_else")
    )
    body = r.json()
    assert body["decision"] == "BLOCK"
    assert body["reason_code"] == "INVALID_MANDATE"
    assert "customer" in body["explanation"].lower()


def test_post_evaluate_block_invalid_mandate(api):
    client, session = api
    _seeded(session)

    r = client.post("/warden/evaluate", json=_payload(mandate_id="man_ghost"))
    body = r.json()
    assert body["decision"] == "BLOCK"
    assert body["reason_code"] == "INVALID_MANDATE"


def test_post_evaluate_block_after_transaction_limit(api):
    client, session = api
    _seeded(session)

    # Mandate A has tx_limit=1. First ALLOW should reserve the slot; second
    # ALLOWable proposal for the same mandate should BLOCK on frequency.
    r1 = client.post("/warden/evaluate", json=_payload(idempotency_key="idem_freq_1")).json()
    assert r1["decision"] == "ALLOW"

    r2 = client.post(
        "/warden/evaluate",
        json=_payload(
            amount="200.00",
            quoted_price="200.00",
            current_price="200.00",
            idempotency_key="idem_freq_2",
        ),
    ).json()
    # Once the mandate is EXHAUSTED, the status check catches it first with the
    # WINDOW_EXHAUSTED reason (or CAP_EXCEEDED if the previous ALLOW consumed
    # the entire cap). Both are legitimate; assert it is a BLOCK either way.
    assert r2["decision"] == "BLOCK"
    assert r2["reason_code"] in {"WINDOW_EXHAUSTED", "CAP_EXCEEDED"}


def test_approve_endpoint_transitions_step_up_action(api):
    client, session = api
    _seeded(session)

    stepup = client.post(
        "/warden/evaluate",
        json=_payload(
            mandate_id="man_B_bulk_5k",
            customer_id="cust_bulk_buyer",
            amount="2500.00",
            quoted_price="2500.00",
            current_price="2500.00",
            idempotency_key="idem_api_stepup2",
        ),
    ).json()
    assert stepup["decision"] == "STEP_UP"

    r = client.post(f"/warden/approve/{stepup['action_id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "STEP_UP_APPROVED"


def test_approve_endpoint_rejects_non_stepup(api):
    client, session = api
    _seeded(session)

    ok = client.post("/warden/evaluate", json=_payload(idempotency_key="idem_api_ok")).json()
    r = client.post(f"/warden/approve/{ok['action_id']}")
    assert r.status_code == 409


def test_approve_endpoint_404_when_action_missing(api):
    client, session = api
    _seeded(session)
    r = client.post("/warden/approve/act_missing")
    assert r.status_code == 404


def test_revoke_endpoint_marks_revoked_and_subsequent_proposals_block(api):
    client, session = api
    _seeded(session)

    r = client.post("/warden/revoke-mandate/man_A_regular_2k")
    assert r.status_code == 200
    assert r.json()["status"] == "REVOKED"

    evaluate = client.post(
        "/warden/evaluate",
        json=_payload(idempotency_key="idem_after_api_revoke"),
    ).json()
    assert evaluate["decision"] == "BLOCK"
    assert evaluate["reason_code"] == "MANDATE_REVOKED"


def test_get_mandate_endpoint(api):
    client, session = api
    _seeded(session)
    r = client.get("/warden/mandate/man_A_regular_2k")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "man_A_regular_2k"
    assert body["status"] == "ACTIVE"
    assert body["allowed_categories"] == ["coffee"]


def test_get_mandate_404(api):
    client, session = api
    _seeded(session)
    r = client.get("/warden/mandate/man_ghost")
    assert r.status_code == 404


def test_get_action_endpoint(api):
    client, session = api
    _seeded(session)
    created = client.post(
        "/warden/evaluate", json=_payload(idempotency_key="idem_api_get")
    ).json()

    r = client.get(f"/warden/action/{created['action_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["action"]["id"] == created["action_id"]
    assert body["decision"] is not None
    assert body["decision"]["result"] == "ALLOW"


def test_get_action_404(api):
    client, session = api
    _seeded(session)
    r = client.get("/warden/action/act_missing")
    assert r.status_code == 404
