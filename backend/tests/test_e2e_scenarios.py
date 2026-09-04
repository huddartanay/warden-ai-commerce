"""
End-to-end scenarios A / B / C from the Stage 5 spec.

Every scenario runs the FULL stack — Buyer Agent → Warden → payment layer —
over HTTP via the FastAPI TestClient with the deterministic Razorpay mock.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import RazorpayRef
from app.seed import seed_data


def _seeded(session):
    seed_data(session)
    session.commit()


# ---- Scenario A: ALLOW -> Razorpay order created ---------------------------


def test_scenario_a_allowed_purchase_creates_razorpay_order(api):
    """
    ₹1499 restock against mandate A (cap ₹2000). Warden ALLOWs, the agent
    auto-executes payment, and a Razorpay order + payment link are recorded.
    """
    client, session = api
    _seeded(session)

    r = client.post(
        "/agent/purchase-intent",
        json={
            "natural_language": "Restock my coffee. Spend up to ₹2000.",
            "customer_id": "cust_priya_regular",
            "idempotency_key": "scenario_A",
        },
    )
    assert r.status_code == 200
    body = r.json()

    # Warden allowed.
    assert body["warden"]["decision"] == "ALLOW"
    assert body["agent_verdict"] == "ALLOW"

    # Razorpay was called and recorded.
    assert body["payment"] is not None, "payment envelope should be populated on ALLOW"
    assert "error" not in body["payment"]
    assert body["payment"]["order"]["razorpay_id"].startswith("order_MOCK")
    assert body["payment"]["payment_link"]["razorpay_id"].startswith("plink_MOCK")
    assert body["payment"]["action_status"] == "PAYMENT_INITIATED"

    # Verify RazorpayRef rows persisted.
    action_id = body["warden"]["action_id"]
    refs = (
        session.execute(select(RazorpayRef).where(RazorpayRef.action_id == action_id))
        .scalars()
        .all()
    )
    types = sorted([r.ref_type for r in refs])
    assert types == ["order", "payment_link"]

    # /warden/action bundles action + decision + refs together.
    got = client.get(f"/warden/action/{action_id}").json()
    assert got["action"]["status"] == "PAYMENT_INITIATED"
    assert sorted(r["ref_type"] for r in got["razorpay_refs"]) == ["order", "payment_link"]


# ---- Scenario B: BLOCK -> Razorpay is NOT called ---------------------------


def test_scenario_b_blocked_purchase_does_not_call_razorpay(api):
    """
    ₹3499 coffee machine against mandate A (coffee-only, ₹2000 cap). Warden
    BLOCKs. Razorpay must NOT be invoked. No RazorpayRef rows exist.
    """
    client, session = api
    _seeded(session)

    r = client.post(
        "/agent/build-cart",
        json={
            "customer_id": "cust_priya_regular",
            "items": [{"catalog_item_id": "cat_coffee_machine", "quantity": 1}],
            "idempotency_key": "scenario_B",
        },
    )
    assert r.status_code == 200
    body = r.json()

    # Warden blocked (category mismatch — coffee_machine is category='appliance').
    assert body["warden"]["decision"] == "BLOCK"
    assert body["warden"]["reason_code"] == "OUT_OF_SCOPE_CATEGORY"

    # No Razorpay refs were ever created.
    total_refs = session.scalar(select(func.count()).select_from(RazorpayRef))
    assert total_refs == 0

    # Explicitly attempting to execute payment on the BLOCKED action fails.
    action_id = body["warden"]["action_id"]
    r = client.post(f"/warden/execute-payment/{action_id}")
    assert r.status_code == 409  # invalid state
    assert "cannot execute payment" in r.json()["detail"]


# ---- Scenario C: same allowed action twice -> duplicate ---------------------


def test_scenario_c_duplicate_intent_returns_same_action_no_extra_razorpay_call(api):
    """
    Same idempotency_key submitted twice. Warden's own short-circuit returns
    the same action; the payment layer returns the same order + link without
    a new Razorpay call.
    """
    client, session = api
    _seeded(session)

    payload = {
        "natural_language": "Restock my coffee. Spend up to ₹2000.",
        "customer_id": "cust_priya_regular",
        "idempotency_key": "scenario_C",
    }

    first = client.post("/agent/purchase-intent", json=payload).json()
    second = client.post("/agent/purchase-intent", json=payload).json()

    # Same action.
    assert first["warden"]["decision"] == "ALLOW"
    assert first["payment"]["order"]["razorpay_id"].startswith("order_MOCK")

    assert second["warden"]["action_id"] == first["warden"]["action_id"]
    assert second["warden"]["duplicate"] is True
    assert second["payment"]["order"]["razorpay_id"] == first["payment"]["order"]["razorpay_id"]
    assert second["payment"]["duplicate"] is True

    # Exactly ONE order + ONE payment_link exist in the DB — no doubles.
    action_id = first["warden"]["action_id"]
    types = sorted(
        r.ref_type
        for r in session.execute(
            select(RazorpayRef).where(RazorpayRef.action_id == action_id)
        )
        .scalars()
        .all()
    )
    assert types == ["order", "payment_link"]
