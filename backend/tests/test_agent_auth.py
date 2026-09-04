"""
Stage 7 (2/4) — agent identity + HMAC signing.

Every proposal from an AI Buyer Agent must be signed. Bad or missing
signatures are BLOCK AGENT_AUTH_FAILED and never reach the policy engine.
A valid signature for a different mandate is also rejected.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.audit import events
from app.models import Action, AuditLog
from app.models.enums import DecisionResult, ReasonCode
from app.seed import seed_data
from app.warden import (
    Proposal,
    create_credential,
    evaluate_proposal,
    sign_proposal,
)


def _seeded(session):
    seed_data(session)
    session.commit()


def _proposal(**overrides) -> Proposal:
    defaults = dict(
        mandate_id="man_A_regular_2k",
        customer_id="cust_priya_regular",
        merchant_id="mer_priya_coffee",
        cart_id="cart_auth_1",
        amount=Decimal("500.00"),
        currency="INR",
        category="coffee",
        quoted_price=Decimal("500.00"),
        current_price=Decimal("500.00"),
        idempotency_key="auth_1",
    )
    defaults.update(overrides)
    return Proposal(**defaults)


def _signing_payload(p: Proposal) -> dict:
    from app.warden.coordinator import _proposal_signing_payload

    return _proposal_signing_payload(p)


def _issue_agent(session, agent_id: str, mandate_id: str) -> str:
    _, secret = create_credential(
        session, agent_id=agent_id, mandate_id=mandate_id
    )
    session.commit()
    return secret


# ---- Required tests --------------------------------------------------------


def test_unsigned_proposal_blocked(session):
    """Providing agent_id without a signature is an immediate BLOCK."""
    _seeded(session)
    _issue_agent(session, "agt_A", "man_A_regular_2k")

    proposal = _proposal(idempotency_key="unsigned_1")
    out = evaluate_proposal(session, proposal, agent_id="agt_A", signature=None)
    session.commit()

    assert out.decision == DecisionResult.BLOCK
    assert out.reason_code == ReasonCode.AGENT_AUTH_FAILED

    # Recorded as an action + emitted AGENT_AUTH_FAILED + BLOCKED events.
    audit_types = [
        r.event_type
        for r in session.execute(
            select(AuditLog)
            .where(AuditLog.action_id == out.action_id)
            .order_by(AuditLog.seq.asc())
        )
        .scalars()
        .all()
    ]
    assert events.AGENT_AUTH_FAILED in audit_types
    assert events.BLOCKED in audit_types
    # WARDEN_EVALUATED must NOT fire — the engine was never invoked.
    assert events.WARDEN_EVALUATED not in audit_types


def test_signature_from_wrong_agent_blocked(session):
    """
    A valid signature for mandate A cannot authorize a proposal targeting
    mandate B, even if the HMAC is correctly formed with agent A's secret.
    """
    _seeded(session)
    secret_a = _issue_agent(session, "agt_A", "man_A_regular_2k")

    # Craft a proposal for mandate B and sign it with agent A's key.
    proposal = _proposal(
        mandate_id="man_B_bulk_5k",
        customer_id="cust_bulk_buyer",
        idempotency_key="wrongmandate_1",
    )
    signature = sign_proposal(secret_a, _signing_payload(proposal))

    out = evaluate_proposal(
        session, proposal, agent_id="agt_A", signature=signature
    )
    session.commit()

    assert out.decision == DecisionResult.BLOCK
    assert out.reason_code == ReasonCode.AGENT_AUTH_FAILED
    assert "scoped to mandate" in out.explanation


def test_valid_signature_reaches_policy_engine(session):
    _seeded(session)
    secret = _issue_agent(session, "agt_A", "man_A_regular_2k")

    proposal = _proposal(idempotency_key="signed_ok_1")
    signature = sign_proposal(secret, _signing_payload(proposal))

    out = evaluate_proposal(
        session, proposal, agent_id="agt_A", signature=signature
    )
    session.commit()

    # Auth passed -> engine ran -> policy decided ALLOW.
    assert out.decision == DecisionResult.ALLOW
    assert out.reason_code == ReasonCode.OK

    audit_types = [
        r.event_type
        for r in session.execute(
            select(AuditLog).where(AuditLog.action_id == out.action_id)
        )
        .scalars()
        .all()
    ]
    assert events.WARDEN_EVALUATED in audit_types
    assert events.AGENT_AUTH_FAILED not in audit_types


# ---- Additional safety --------------------------------------------------------


def test_tampered_signature_blocked(session):
    """Flipping any byte of the signature is rejected."""
    _seeded(session)
    secret = _issue_agent(session, "agt_A", "man_A_regular_2k")

    proposal = _proposal(idempotency_key="tampered_1")
    good = sign_proposal(secret, _signing_payload(proposal))
    bad = good[:-1] + ("0" if good[-1] != "0" else "1")

    out = evaluate_proposal(
        session, proposal, agent_id="agt_A", signature=bad
    )
    session.commit()
    assert out.decision == DecisionResult.BLOCK
    assert out.reason_code == ReasonCode.AGENT_AUTH_FAILED
    assert "Signature mismatch" in out.explanation


def test_signature_check_runs_before_policy_engine(session):
    """
    A signed-but-invalid proposal that would ALSO fail a policy check
    (e.g. over cap) must still surface AGENT_AUTH_FAILED — the auth gate
    fires first and the engine never runs.
    """
    _seeded(session)
    _issue_agent(session, "agt_A", "man_A_regular_2k")

    proposal = _proposal(
        amount=Decimal("9999.00"),  # would trigger CAP_EXCEEDED
        idempotency_key="auth_first_1",
    )
    out = evaluate_proposal(
        session, proposal, agent_id="agt_A", signature="deadbeef"
    )
    session.commit()
    assert out.decision == DecisionResult.BLOCK
    assert out.reason_code == ReasonCode.AGENT_AUTH_FAILED  # NOT CAP_EXCEEDED


def test_unsigned_proposal_from_system_still_works(session):
    """
    Backwards-compatibility: no agent_id + no signature = system/direct
    call. All Stages 1-6 tests use this path and must keep working.
    """
    _seeded(session)
    out = evaluate_proposal(session, _proposal(idempotency_key="system_1"))
    session.commit()
    assert out.decision == DecisionResult.ALLOW


# ---- HTTP surface ----------------------------------------------------------


def test_evaluate_endpoint_accepts_signed_headers(api):
    client, session = api
    _seeded(session)
    secret = _issue_agent(session, "agt_A", "man_A_regular_2k")

    payload = {
        "mandate_id": "man_A_regular_2k",
        "customer_id": "cust_priya_regular",
        "merchant_id": "mer_priya_coffee",
        "cart_id": "cart_http_auth",
        "amount": "500.00",
        "currency": "INR",
        "category": "coffee",
        "quoted_price": "500.00",
        "current_price": "500.00",
        "idempotency_key": "http_auth_1",
    }
    signature = sign_proposal(secret, payload)

    r = client.post(
        "/warden/evaluate",
        json=payload,
        headers={"X-Agent-Id": "agt_A", "X-Agent-Signature": signature},
    )
    body = r.json()
    assert body["decision"] == "ALLOW"


def test_evaluate_endpoint_rejects_unsigned_when_agent_header_present(api):
    client, session = api
    _seeded(session)
    _issue_agent(session, "agt_A", "man_A_regular_2k")

    payload = {
        "mandate_id": "man_A_regular_2k",
        "customer_id": "cust_priya_regular",
        "merchant_id": "mer_priya_coffee",
        "cart_id": "cart_http_unsig",
        "amount": "500.00",
        "currency": "INR",
        "category": "coffee",
        "quoted_price": "500.00",
        "current_price": "500.00",
        "idempotency_key": "http_unsig_1",
    }
    r = client.post(
        "/warden/evaluate",
        json=payload,
        headers={"X-Agent-Id": "agt_A"},  # signature header intentionally omitted
    )
    body = r.json()
    assert body["decision"] == "BLOCK"
    assert body["reason_code"] == "AGENT_AUTH_FAILED"
