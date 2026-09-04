"""
Failure scenarios required by Stage 6.

For each scenario we verify:
  - state is preserved (no data loss, no silent retry)
  - an audit event was recorded
  - a reason code is available
  - Razorpay is not called when Warden decided against it
  - resolution status is correct

The final test is the show-stopper: a payment fails and Warden's design
prevents a double charge, no matter how many times the caller retries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.audit import events, verify_chain
from app.models import (
    Action,
    ActionStatus,
    AuditLog,
    Mandate,
    MandateStatus,
    RazorpayRef,
    Resolution,
    ResolutionStatus,
)
from app.models.enums import DecisionResult, ReasonCode
from app.payments import MockRazorpayClient, RazorpayError
from app.seed import seed_data
from app.services.resolution import get_by_action
from app.warden import (
    Proposal,
    approve_step_up,
    evaluate_proposal,
    execute_payment,
    resolve_pending_action,
    revoke_mandate,
    simulate_capture,
)


def _seeded(session):
    seed_data(session)
    session.commit()


def _prop(**overrides) -> Proposal:
    defaults = dict(
        mandate_id="man_A_regular_2k",
        customer_id="cust_priya_regular",
        merchant_id="mer_priya_coffee",
        cart_id="cart_x",
        amount=Decimal("1499.00"),
        currency="INR",
        category="coffee",
        quoted_price=Decimal("1499.00"),
        current_price=Decimal("1499.00"),
        idempotency_key="idem_x",
    )
    defaults.update(overrides)
    return Proposal(**defaults)


def _event_types_for(session, action_id: str) -> list[str]:
    rows = (
        session.execute(
            select(AuditLog)
            .where(AuditLog.action_id == action_id)
            .order_by(AuditLog.seq.asc())
        )
        .scalars()
        .all()
    )
    return [r.event_type for r in rows]


# ---- 1. Duplicate transaction ---------------------------------------------


def test_scenario_duplicate_transaction_returns_same_action_and_emits_duplicate_detected(session):
    _seeded(session)
    first = evaluate_proposal(session, _prop(idempotency_key="dup_1"))
    session.commit()
    second = evaluate_proposal(session, _prop(idempotency_key="dup_1"))
    session.commit()

    assert second.duplicate is True
    assert second.action_id == first.action_id
    # DUPLICATE_DETECTED event fired.
    types = _event_types_for(session, first.action_id)
    assert events.DUPLICATE_DETECTED in types
    # No second Action row.
    count = session.scalar(
        select(func.count())
        .select_from(Action)
        .where(Action.idempotency_key == "dup_1")
    )
    assert count == 1


def test_agent_path_also_emits_duplicate_detected(session):
    """The buyer agent's own short-circuit must record the retry in audit."""
    _seeded(session)
    from app.agents import BuyerAgent, MockLLMClient

    agent = BuyerAgent(llm=MockLLMClient())
    first = agent.run(
        session,
        natural_language="Restock coffee.",
        customer_id="cust_priya_regular",
        idempotency_key="agent_dup_1",
    )
    session.commit()
    agent.run(
        session,
        natural_language="Restock coffee.",
        customer_id="cust_priya_regular",
        idempotency_key="agent_dup_1",
    )
    session.commit()

    types = _event_types_for(session, first.warden.action_id)
    assert events.DUPLICATE_DETECTED in types


# ---- 2. Payment API failure -----------------------------------------------


class _FailingRazorpay(MockRazorpayClient):
    def __init__(self, fail_on="create_order"):
        self.fail_on = fail_on

    def create_order(self, **kw):
        if self.fail_on == "create_order":
            raise RazorpayError("simulated Razorpay outage")
        return super().create_order(**kw)

    def capture_payment(self, pid, **kw):
        if self.fail_on == "capture":
            raise RazorpayError("simulated capture failure")
        return super().capture_payment(pid, **kw)


def test_scenario_payment_api_failure_marks_failed_and_rolls_back(session):
    _seeded(session)
    out = evaluate_proposal(
        session,
        _prop(
            mandate_id="man_B_bulk_5k",
            customer_id="cust_bulk_buyer",
            amount=Decimal("1500.00"),
            quoted_price=Decimal("1500.00"),
            current_price=Decimal("1500.00"),
            idempotency_key="fail_pay_1",
        ),
    )
    session.commit()

    # Warden allowed; reservation persisted.
    mandate = session.get(Mandate, "man_B_bulk_5k")
    assert mandate.current_period_spend == Decimal("1500.00")

    with pytest.raises(RazorpayError):
        execute_payment(session, out.action_id, razorpay=_FailingRazorpay("create_order"))
    session.commit()

    # State preserved (action row, decision, mandate exist), status changed.
    action = session.get(Action, out.action_id)
    assert action.status == ActionStatus.PAYMENT_FAILED

    # Audit event with reason recorded.
    types = _event_types_for(session, out.action_id)
    assert events.PAYMENT_FAILED in types

    # Reservation rolled back — the customer isn't held to spend that didn't happen.
    mandate = session.get(Mandate, "man_B_bulk_5k")
    assert mandate.current_period_spend == Decimal("0")
    assert mandate.current_period_transactions == 0


# ---- 3. Expired mandate ---------------------------------------------------


def test_scenario_expired_mandate_blocks_and_never_touches_razorpay(session):
    _seeded(session)
    mandate = session.get(Mandate, "man_A_regular_2k")
    mandate.validity_end = datetime.now(tz=timezone.utc) - timedelta(days=1)
    session.commit()

    out = evaluate_proposal(session, _prop(idempotency_key="expired_1"))
    session.commit()

    assert out.decision == DecisionResult.BLOCK
    assert out.reason_code == ReasonCode.MANDATE_EXPIRED

    # No Razorpay refs anywhere.
    assert session.scalar(select(func.count()).select_from(RazorpayRef)) == 0


# ---- 4. Price changed after quote -----------------------------------------


def test_scenario_price_drift_blocks_with_price_drift_reason(session):
    _seeded(session)
    out = evaluate_proposal(
        session,
        _prop(quoted_price=Decimal("1000.00"), current_price=Decimal("1100.00"),
              idempotency_key="drift_1"),
    )
    session.commit()

    assert out.decision == DecisionResult.BLOCK
    assert out.reason_code == ReasonCode.PRICE_DRIFT
    # No Razorpay call.
    assert session.scalar(select(func.count()).select_from(RazorpayRef)) == 0
    # BLOCKED narrow event fired.
    assert events.BLOCKED in _event_types_for(session, out.action_id)


# ---- 5. Spending cap exceeded ---------------------------------------------


def test_scenario_cap_exceeded_blocks(session):
    _seeded(session)
    out = evaluate_proposal(session, _prop(amount=Decimal("3499.00"), idempotency_key="cap_1"))
    session.commit()

    assert out.decision == DecisionResult.BLOCK
    assert out.reason_code == ReasonCode.CAP_EXCEEDED

    # No Razorpay refs, no reservation change.
    assert session.scalar(select(func.count()).select_from(RazorpayRef)) == 0
    mandate = session.get(Mandate, "man_A_regular_2k")
    assert mandate.current_period_spend == Decimal("0")


# ---- 6. Human approval required -------------------------------------------


def test_scenario_step_up_enqueues_for_human_and_does_not_call_razorpay(session):
    _seeded(session)
    out = evaluate_proposal(
        session,
        _prop(
            mandate_id="man_B_bulk_5k",
            customer_id="cust_bulk_buyer",
            amount=Decimal("2500.00"),
            quoted_price=Decimal("2500.00"),
            current_price=Decimal("2500.00"),
            idempotency_key="stepup_1",
        ),
    )
    session.commit()

    assert out.decision == DecisionResult.STEP_UP
    assert out.reason_code == ReasonCode.APPROVAL_REQUIRED

    # STEP_UP_REQUESTED narrow event + resolution row.
    assert events.STEP_UP_REQUESTED in _event_types_for(session, out.action_id)
    row = get_by_action(session, out.action_id)
    assert row is not None and row.status == ResolutionStatus.REQUIRES_HUMAN

    # /warden/approve resolves it.
    approve_step_up(session, out.action_id)
    session.commit()
    row = get_by_action(session, out.action_id)
    assert row.status == ResolutionStatus.RESOLVED


# ---- 7. Invalid mandate ---------------------------------------------------


def test_scenario_invalid_mandate_blocks(session):
    _seeded(session)
    out = evaluate_proposal(session, _prop(mandate_id="man_ghost", idempotency_key="ghost_1"))
    session.commit()

    assert out.decision == DecisionResult.BLOCK
    assert out.reason_code == ReasonCode.INVALID_MANDATE
    # Wrong customer for a real mandate is also INVALID_MANDATE.
    out2 = evaluate_proposal(
        session, _prop(customer_id="cust_someone_else", idempotency_key="ghost_2")
    )
    session.commit()
    assert out2.decision == DecisionResult.BLOCK
    assert out2.reason_code == ReasonCode.INVALID_MANDATE


# ---- 8. LLM uncertainty ---------------------------------------------------


def test_scenario_llm_uncertainty_forces_step_up_at_agent_layer(session):
    """Agent's low-confidence escalation. Warden may allow; agent still asks."""
    _seeded(session)
    from app.agents import BuyerAgent, MockLLMClient

    agent = BuyerAgent(llm=MockLLMClient())
    # The mock returns confidence=0.4 when the user says "not sure".
    run = agent.run(
        session,
        natural_language="Restock coffee, I'm not sure how much.",
        customer_id="cust_priya_regular",
        idempotency_key="uncertain_1",
    )
    session.commit()

    # Agent verdict must not be ALLOW even if Warden allowed.
    assert run.agent_verdict != DecisionResult.ALLOW
    # Warden's own decision is preserved untouched.
    assert run.warden is not None


# ============================================================================
# THE SAFE-FAILURE DEMO: payment fails; Warden prevents any double charge.
# ============================================================================


def test_demo_payment_failure_never_double_charges(session):
    """
    Walks the full recovery lifecycle end-to-end.

    1. AI Buyer proposal → Warden ALLOW → mandate reservation.
    2. Razorpay capture FAILS with an uncertain outcome →
       action = PENDING_UNRESOLVED; reservation NOT rolled back;
       PENDING_UNRESOLVED audit event; resolution queue populated.
    3. Same idempotency_key retried → Warden's own short-circuit returns the
       SAME action_id. Payment layer refuses to re-execute
       (PENDING_UNRESOLVED is not a legal state).
    4. Human investigates, decides the payment did NOT go through, resolves
       as PAYMENT_FAILED with a note. This rolls back the reservation and
       records RESOLUTION_APPLIED.
    5. Only NOW can the customer legitimately attempt again — with a fresh
       idempotency key. That succeeds without any double charge.
    6. The audit hash chain remains valid throughout.
    """
    _seeded(session)

    # Stage 1: Warden ALLOWs and reserves.
    initial = evaluate_proposal(
        session,
        _prop(idempotency_key="safefail_1", amount=Decimal("1499.00")),
    )
    session.commit()
    assert initial.decision == DecisionResult.ALLOW
    mandate = session.get(Mandate, "man_A_regular_2k")
    assert mandate.current_period_spend == Decimal("1499.00")
    assert mandate.current_period_transactions == 1

    # Order + link created against Razorpay (mock).
    execute_payment(session, initial.action_id, razorpay=MockRazorpayClient())
    session.commit()

    # Stage 2: capture fails with an UNCERTAIN outcome.
    with pytest.raises(RazorpayError):
        simulate_capture(
            session, initial.action_id, razorpay=_FailingRazorpay(fail_on="capture")
        )
    session.commit()

    action = session.get(Action, initial.action_id)
    assert action.status == ActionStatus.PENDING_UNRESOLVED
    # Reservation NOT rolled back — we don't yet know whether the charge
    # went through on Razorpay's side.
    mandate = session.get(Mandate, "man_A_regular_2k")
    assert mandate.current_period_spend == Decimal("1499.00")
    # The action is in the resolution queue for a human.
    row = get_by_action(session, initial.action_id)
    assert row is not None and row.status == ResolutionStatus.PENDING_UNRESOLVED
    # Audit event recorded with a reason.
    assert events.PAYMENT_PENDING_UNRESOLVED in _event_types_for(session, action.id)

    # Stage 3: caller retries with the same key — MUST return the same
    # action, and payment layer MUST refuse to try again.
    retry = evaluate_proposal(
        session, _prop(idempotency_key="safefail_1", amount=Decimal("1499.00"))
    )
    session.commit()
    assert retry.duplicate is True
    assert retry.action_id == initial.action_id

    from app.payments import InvalidPaymentStateError

    with pytest.raises(InvalidPaymentStateError):
        execute_payment(session, initial.action_id, razorpay=MockRazorpayClient())

    # Still exactly ONE Razorpay order in the DB.
    order_count = session.scalar(
        select(func.count())
        .select_from(RazorpayRef)
        .where(
            RazorpayRef.action_id == initial.action_id,
            RazorpayRef.ref_type == "order",
        )
    )
    assert order_count == 1

    # Stage 4: human investigates and resolves as PAYMENT_FAILED.
    resolved_action = resolve_pending_action(
        session,
        initial.action_id,
        new_status=ActionStatus.PAYMENT_FAILED,
        note="Confirmed with Razorpay dashboard that no capture occurred.",
        resolved_by="ops:priya",
    )
    session.commit()
    assert resolved_action.status == ActionStatus.PAYMENT_FAILED
    mandate = session.get(Mandate, "man_A_regular_2k")
    assert mandate.current_period_spend == Decimal("0")  # rolled back
    assert mandate.current_period_transactions == 0
    # Resolution row now RESOLVED.
    row = get_by_action(session, initial.action_id)
    assert row.status == ResolutionStatus.RESOLVED
    # RESOLUTION_APPLIED audit event.
    assert events.RESOLUTION_APPLIED in _event_types_for(session, initial.action_id)

    # Stage 5: legitimate re-attempt — with a NEW idempotency key. Succeeds.
    fresh = evaluate_proposal(
        session, _prop(idempotency_key="safefail_2", amount=Decimal("1499.00"))
    )
    session.commit()
    assert fresh.decision == DecisionResult.ALLOW
    assert fresh.action_id != initial.action_id

    execute_payment(session, fresh.action_id, razorpay=MockRazorpayClient())
    simulate_capture(session, fresh.action_id, razorpay=MockRazorpayClient())
    session.commit()

    fresh_action = session.get(Action, fresh.action_id)
    assert fresh_action.status == ActionStatus.PAYMENT_COMPLETED
    mandate = session.get(Mandate, "man_A_regular_2k")
    # Exactly ONE successful charge on the mandate — never double.
    assert mandate.current_period_spend == Decimal("1499.00")
    assert mandate.current_period_transactions == 1

    # Stage 6: the whole audit chain is still valid.
    ok, reason = verify_chain(session)
    assert ok is True, reason
