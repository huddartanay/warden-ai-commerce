"""HTTP tests for the audit + resolution surface."""

from __future__ import annotations

from app.audit import events
from app.models import AuditLog
from app.seed import seed_data


def _seeded(session):
    seed_data(session)
    session.commit()


# ---- /audit/verify --------------------------------------------------------


def test_audit_verify_reports_valid_on_a_clean_chain(api):
    client, session = api
    _seeded(session)

    r = client.get("/audit/verify")
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["first_invalid_entry"] is None
    assert body["entries_checked"] >= 3  # at minimum, the 3 MANDATE_CREATED events


def test_audit_verify_detects_tampering(api):
    client, session = api
    _seeded(session)
    # Mutate an entry's payload but leave its stored hash untouched.
    row = session.query(AuditLog).order_by(AuditLog.seq.asc()).first()
    row.event_data = {"tampered": True}
    session.commit()

    r = client.get("/audit/verify")
    body = r.json()
    assert body["valid"] is False
    assert body["first_invalid_entry"] is not None
    assert body["first_invalid_entry"]["reason"] == "current_hash_mismatch"


# ---- /audit/action + /audit/mandate ---------------------------------------


def test_audit_by_action_returns_only_relevant_entries(api):
    client, session = api
    _seeded(session)

    intent = client.post(
        "/agent/purchase-intent",
        json={
            "natural_language": "Restock my coffee.",
            "customer_id": "cust_priya_regular",
            "idempotency_key": "audit_api_1",
        },
    ).json()
    action_id = intent["warden"]["action_id"]

    r = client.get(f"/audit/action/{action_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    event_types = [e["event_type"] for e in body["entries"]]
    assert events.WARDEN_EVALUATED in event_types
    assert events.PAYMENT_CREATED in event_types
    # every returned entry has this action_id
    assert all(e["action_id"] == action_id for e in body["entries"])


def test_audit_by_mandate_includes_creation_and_action_events(api):
    client, session = api
    _seeded(session)

    # Trigger an action against mandate A to generate action-scoped events.
    client.post(
        "/agent/purchase-intent",
        json={
            "natural_language": "Restock my coffee.",
            "customer_id": "cust_priya_regular",
            "idempotency_key": "audit_api_mandate",
        },
    )

    r = client.get("/audit/mandate/man_A_regular_2k")
    body = r.json()
    types = [e["event_type"] for e in body["entries"]]
    assert events.MANDATE_CREATED in types
    assert events.WARDEN_EVALUATED in types


# ---- /audit/resolution-queue + /audit/resolve -----------------------------


def test_resolution_queue_empty_when_all_actions_terminal(api):
    client, session = api
    _seeded(session)
    r = client.get("/audit/resolution-queue")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_step_up_creates_a_requires_human_queue_entry(api):
    client, session = api
    _seeded(session)

    # mandate B step-up threshold = ₹2000; ₹2500 => STEP_UP
    stepup = client.post(
        "/agent/build-cart",
        json={
            "customer_id": "cust_bulk_buyer",
            # 2 * 800 (premium) + 1 * 699 (classic) = 2299 -> above threshold
            "items": [
                {"catalog_item_id": "cat_premium_coffee", "quantity": 2},
                {"catalog_item_id": "cat_classic_coffee", "quantity": 1},
            ],
            "idempotency_key": "audit_stepup_1",
        },
    ).json()
    assert stepup["warden"]["decision"] == "STEP_UP"

    r = client.get("/audit/resolution-queue?status=REQUIRES_HUMAN").json()
    assert r["count"] == 1
    assert r["entries"][0]["action_id"] == stepup["warden"]["action_id"]

    # Approving the action clears the queue.
    client.post(f"/warden/approve/{stepup['warden']['action_id']}")
    r = client.get("/audit/resolution-queue?status=REQUIRES_HUMAN").json()
    assert r["count"] == 0
    r = client.get("/audit/resolution-queue?status=RESOLVED").json()
    assert r["count"] == 1


def test_resolve_missing_action_returns_404(api):
    client, session = api
    _seeded(session)
    r = client.post("/audit/resolve/act_ghost", json={"note": "does not exist"})
    assert r.status_code == 404
