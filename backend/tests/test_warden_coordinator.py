"""
Warden coordinator tests — exercise the DB-integrated service layer:
idempotency short-circuit, ALLOW reserves budget, approve promotes STEP_UP,
revoke marks REVOKED, audit events are written and chain-valid.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.audit import verify_chain
from app.models import (
    Action,
    ActionStatus,
    Decision,
    Mandate,
    MandateStatus,
    ReasonCode,
)
from app.models.audit import AuditLog
from app.models.enums import DecisionResult
from app.seed import seed_data
from app.warden import (
    ActionNotFoundError,
    InvalidActionStateError,
    MandateNotFoundError,
    Proposal,
    approve_step_up,
    evaluate_proposal,
    revoke_mandate,
)


def _seeded(session):
    seed_data(session)
    session.commit()


def _proposal(**overrides) -> Proposal:
    defaults = dict(
        mandate_id="man_A_regular_2k",
        customer_id="cust_priya_regular",
        merchant_id="mer_priya_coffee",
        cart_id="cart_1",
        amount=Decimal("1499.00"),
        currency="INR",
        category="coffee",
        quoted_price=Decimal("1499.00"),
        current_price=Decimal("1499.00"),
        idempotency_key="idem_test_1",
    )
    defaults.update(overrides)
    return Proposal(**defaults)


# ---------------------------------------------------------------- happy path


def test_allow_reserves_budget_and_persists(session):
    _seeded(session)
    out = evaluate_proposal(session, _proposal())
    session.commit()

    assert out.decision == DecisionResult.ALLOW
    assert out.duplicate is False

    action = session.get(Action, out.action_id)
    assert action.status == ActionStatus.ALLOWED

    decision = session.execute(
        Decision.__table__.select().where(Decision.action_id == out.action_id)
    ).first()
    assert decision is not None

    mandate = session.get(Mandate, "man_A_regular_2k")
    assert mandate.current_period_spend == Decimal("1499.00")
    assert mandate.current_period_transactions == 1
    # Mandate A has tx_limit=1, so one ALLOW consumes the whole transaction
    # window and the state machine moves it straight to EXHAUSTED.
    assert mandate.status == MandateStatus.EXHAUSTED


def test_block_does_not_reserve_budget(session):
    _seeded(session)
    out = evaluate_proposal(
        session,
        _proposal(amount=Decimal("3000.00")),  # over ₹2000 cap
    )
    session.commit()

    assert out.decision == DecisionResult.BLOCK
    assert out.reason_code == ReasonCode.CAP_EXCEEDED

    mandate = session.get(Mandate, "man_A_regular_2k")
    assert mandate.current_period_spend == Decimal("0")
    assert mandate.current_period_transactions == 0

    action = session.get(Action, out.action_id)
    assert action.status == ActionStatus.BLOCKED


# ---------------------------------------------------------------- idempotency


def test_duplicate_idempotency_key_returns_same_decision_and_no_new_action(session):
    _seeded(session)

    first = evaluate_proposal(session, _proposal(idempotency_key="dup_key"))
    session.commit()
    assert first.duplicate is False

    # Same key again — should return the same action_id and the same decision,
    # without creating a second Action row.
    second = evaluate_proposal(session, _proposal(idempotency_key="dup_key"))
    session.commit()

    assert second.duplicate is True
    assert second.action_id == first.action_id
    assert second.decision == first.decision
    assert second.reason_code == first.reason_code

    # Verify no second action was created.
    from sqlalchemy import func, select
    count = session.scalar(
        select(func.count()).select_from(Action).where(Action.idempotency_key == "dup_key")
    )
    assert count == 1


def test_duplicate_of_blocked_action_returns_the_same_block(session):
    _seeded(session)

    first = evaluate_proposal(
        session, _proposal(idempotency_key="dup_block", amount=Decimal("9999.00"))
    )
    session.commit()
    assert first.decision == DecisionResult.BLOCK

    second = evaluate_proposal(
        session, _proposal(idempotency_key="dup_block", amount=Decimal("9999.00"))
    )
    session.commit()

    assert second.duplicate is True
    assert second.decision == DecisionResult.BLOCK
    assert second.action_id == first.action_id


# ---------------------------------------------------------------- STEP_UP + approve


def test_step_up_action_can_be_approved_and_then_reserves_budget(session):
    _seeded(session)

    out = evaluate_proposal(
        session,
        _proposal(
            mandate_id="man_B_bulk_5k",
            customer_id="cust_bulk_buyer",
            amount=Decimal("2500.00"),  # over ₹2000 step-up threshold, under ₹5000 cap
            quoted_price=Decimal("2500.00"),
            current_price=Decimal("2500.00"),
            idempotency_key="idem_stepup",
        ),
    )
    session.commit()

    assert out.decision == DecisionResult.STEP_UP
    assert out.reason_code == ReasonCode.APPROVAL_REQUIRED

    # STEP_UP does NOT reserve budget until approval.
    mandate = session.get(Mandate, "man_B_bulk_5k")
    assert mandate.current_period_spend == Decimal("0")
    assert mandate.current_period_transactions == 0

    action = approve_step_up(session, out.action_id)
    session.commit()

    assert action.status == ActionStatus.STEP_UP_APPROVED
    mandate = session.get(Mandate, "man_B_bulk_5k")
    assert mandate.current_period_spend == Decimal("2500.00")
    assert mandate.current_period_transactions == 1
    assert mandate.status == MandateStatus.PARTIALLY_USED


def test_approving_a_non_stepup_action_raises(session):
    _seeded(session)
    out = evaluate_proposal(session, _proposal(idempotency_key="idem_ok"))
    session.commit()
    assert out.decision == DecisionResult.ALLOW

    with pytest.raises(InvalidActionStateError):
        approve_step_up(session, out.action_id)


def test_approving_unknown_action_raises(session):
    _seeded(session)
    with pytest.raises(ActionNotFoundError):
        approve_step_up(session, "act_does_not_exist")


# ---------------------------------------------------------------- revoke


def test_revoking_a_mandate_marks_it_and_blocks_further_proposals(session):
    _seeded(session)
    revoke_mandate(session, "man_A_regular_2k")
    session.commit()

    mandate = session.get(Mandate, "man_A_regular_2k")
    assert mandate.status == MandateStatus.REVOKED

    out = evaluate_proposal(session, _proposal(idempotency_key="idem_after_revoke"))
    session.commit()

    assert out.decision == DecisionResult.BLOCK
    assert out.reason_code == ReasonCode.MANDATE_REVOKED


def test_revoking_unknown_mandate_raises(session):
    _seeded(session)
    with pytest.raises(MandateNotFoundError):
        revoke_mandate(session, "man_does_not_exist")


# ---------------------------------------------------------------- audit


def test_evaluation_writes_audit_event_and_chain_is_valid(session):
    _seeded(session)

    evaluate_proposal(session, _proposal(idempotency_key="idem_audit_1"))
    evaluate_proposal(
        session,
        _proposal(idempotency_key="idem_audit_2", amount=Decimal("9999.00")),
    )
    session.commit()

    rows = session.query(AuditLog).order_by(AuditLog.seq.asc()).all()
    event_types = [r.event_type for r in rows]
    assert event_types.count("WARDEN_EVALUATED") == 2

    ok, reason = verify_chain(session)
    assert ok is True, reason


def test_revoke_emits_mandate_revoked_event(session):
    _seeded(session)
    revoke_mandate(session, "man_A_regular_2k")
    session.commit()

    rows = session.query(AuditLog).order_by(AuditLog.seq.asc()).all()
    assert any(r.event_type == "MANDATE_REVOKED" for r in rows)


def test_approve_emits_human_approved_event(session):
    _seeded(session)
    out = evaluate_proposal(
        session,
        _proposal(
            mandate_id="man_B_bulk_5k",
            customer_id="cust_bulk_buyer",
            amount=Decimal("2500.00"),
            quoted_price=Decimal("2500.00"),
            current_price=Decimal("2500.00"),
            idempotency_key="idem_stepup_audit",
        ),
    )
    approve_step_up(session, out.action_id)
    session.commit()

    types = [r.event_type for r in session.query(AuditLog).all()]
    assert "HUMAN_APPROVED" in types


# ---------------------------------------------------------------- reservation


def test_second_action_sees_reduced_remaining_budget(session):
    _seeded(session)

    first = evaluate_proposal(
        session,
        _proposal(
            mandate_id="man_B_bulk_5k",
            customer_id="cust_bulk_buyer",
            amount=Decimal("1500.00"),
            quoted_price=Decimal("1500.00"),
            current_price=Decimal("1500.00"),
            idempotency_key="idem_reserve_1",
        ),
    )
    second = evaluate_proposal(
        session,
        _proposal(
            mandate_id="man_B_bulk_5k",
            customer_id="cust_bulk_buyer",
            amount=Decimal("4000.00"),  # remaining is only 3500 after first
            quoted_price=Decimal("4000.00"),
            current_price=Decimal("4000.00"),
            idempotency_key="idem_reserve_2",
        ),
    )
    session.commit()

    assert first.decision == DecisionResult.ALLOW
    assert second.decision == DecisionResult.BLOCK
    assert second.reason_code == ReasonCode.CAP_EXCEEDED
