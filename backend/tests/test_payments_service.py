"""Payment service — DB-integrated tests, using the deterministic mock."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import Action, ActionStatus, Mandate, RazorpayRef
from app.models.enums import DecisionResult
from app.payments import (
    InvalidPaymentStateError,
    MockRazorpayClient,
    PaymentActionNotFoundError,
    RazorpayError,
    execute_payment,
    refund_action,
    simulate_capture,
)
from app.seed import seed_data
from app.warden import Proposal, evaluate_proposal


def _seeded(session):
    seed_data(session)
    session.commit()


def _proposal(**overrides) -> Proposal:
    defaults = dict(
        mandate_id="man_A_regular_2k",
        customer_id="cust_priya_regular",
        merchant_id="mer_priya_coffee",
        cart_id="cart_pay_1",
        amount=Decimal("1499.00"),
        currency="INR",
        category="coffee",
        quoted_price=Decimal("1499.00"),
        current_price=Decimal("1499.00"),
        idempotency_key="idem_pay_1",
    )
    defaults.update(overrides)
    return Proposal(**defaults)


class _FailingRazorpayClient:
    """create_order raises. Used to exercise the failure path."""

    def create_order(self, **kw):
        raise RazorpayError("simulated network failure")

    def create_payment_link(self, **kw):
        raise RazorpayError("should not be called")

    def fetch_payment(self, pid):
        raise RazorpayError("should not be called")

    def capture_payment(self, pid, **kw):
        raise RazorpayError("simulated capture failure")

    def refund_payment(self, pid, **kw):
        raise RazorpayError("simulated refund failure")


# ---- execute_payment ------------------------------------------------------


def test_execute_payment_on_allowed_action_creates_order_and_link(session):
    _seeded(session)
    out = evaluate_proposal(session, _proposal())
    session.commit()
    assert out.decision == DecisionResult.ALLOW

    result = execute_payment(session, out.action_id, razorpay=MockRazorpayClient())
    session.commit()

    assert result.action_status == ActionStatus.PAYMENT_INITIATED
    assert result.order is not None
    assert result.order.razorpay_id.startswith("order_MOCK")
    assert result.payment_link is not None
    assert result.payment_link.razorpay_id.startswith("plink_MOCK")
    assert result.duplicate is False

    action = session.get(Action, out.action_id)
    assert action.status == ActionStatus.PAYMENT_INITIATED


def test_execute_payment_is_idempotent(session):
    _seeded(session)
    out = evaluate_proposal(session, _proposal(idempotency_key="idem_pay_dup"))
    session.commit()

    first = execute_payment(session, out.action_id, razorpay=MockRazorpayClient())
    session.commit()
    second = execute_payment(session, out.action_id, razorpay=MockRazorpayClient())
    session.commit()

    assert second.duplicate is True
    assert second.order.razorpay_id == first.order.razorpay_id
    assert second.payment_link.razorpay_id == first.payment_link.razorpay_id

    # No duplicate RazorpayRef rows.
    from sqlalchemy import func, select

    n = session.scalar(
        select(func.count()).select_from(RazorpayRef).where(RazorpayRef.action_id == out.action_id)
    )
    assert n == 2  # one order + one payment_link


def test_execute_payment_rejects_non_allowed_action(session):
    _seeded(session)
    out = evaluate_proposal(
        session, _proposal(amount=Decimal("9999.00"), idempotency_key="idem_pay_blocked")
    )
    session.commit()
    assert out.decision == DecisionResult.BLOCK

    with pytest.raises(InvalidPaymentStateError):
        execute_payment(session, out.action_id, razorpay=MockRazorpayClient())


def test_execute_payment_missing_action_raises(session):
    _seeded(session)
    with pytest.raises(PaymentActionNotFoundError):
        execute_payment(session, "act_missing", razorpay=MockRazorpayClient())


def test_execute_payment_razorpay_failure_marks_failed_and_rolls_back(session):
    _seeded(session)

    # Fresh ALLOW reserves budget on mandate B (₹5000 cap, tx_limit=2).
    out = evaluate_proposal(
        session,
        _proposal(
            mandate_id="man_B_bulk_5k",
            customer_id="cust_bulk_buyer",
            amount=Decimal("1500.00"),
            quoted_price=Decimal("1500.00"),
            current_price=Decimal("1500.00"),
            idempotency_key="idem_pay_fail",
        ),
    )
    session.commit()
    assert out.decision == DecisionResult.ALLOW

    mandate = session.get(Mandate, "man_B_bulk_5k")
    assert mandate.current_period_spend == Decimal("1500.00")
    assert mandate.current_period_transactions == 1

    with pytest.raises(RazorpayError):
        execute_payment(session, out.action_id, razorpay=_FailingRazorpayClient())
    session.commit()

    # Action moved to PAYMENT_FAILED.
    action = session.get(Action, out.action_id)
    assert action.status == ActionStatus.PAYMENT_FAILED

    # Mandate reservation rolled back.
    mandate = session.get(Mandate, "man_B_bulk_5k")
    assert mandate.current_period_spend == Decimal("0")
    assert mandate.current_period_transactions == 0


# ---- simulate_capture -----------------------------------------------------


def test_simulate_capture_moves_to_payment_completed(session):
    _seeded(session)
    out = evaluate_proposal(session, _proposal(idempotency_key="idem_cap_1"))
    session.commit()
    execute_payment(session, out.action_id, razorpay=MockRazorpayClient())
    session.commit()

    result = simulate_capture(session, out.action_id, razorpay=MockRazorpayClient())
    session.commit()

    assert result.action_status == ActionStatus.PAYMENT_COMPLETED
    assert result.payment.status == "captured"

    action = session.get(Action, out.action_id)
    assert action.status == ActionStatus.PAYMENT_COMPLETED


def test_simulate_capture_rejects_wrong_state(session):
    _seeded(session)
    out = evaluate_proposal(session, _proposal(idempotency_key="idem_cap_wrong"))
    session.commit()
    # Never called execute_payment -> action is ALLOWED, not PAYMENT_INITIATED.
    with pytest.raises(InvalidPaymentStateError):
        simulate_capture(session, out.action_id, razorpay=MockRazorpayClient())


def test_simulate_capture_failure_marks_pending_unresolved(session):
    _seeded(session)
    out = evaluate_proposal(session, _proposal(idempotency_key="idem_cap_fail"))
    session.commit()
    execute_payment(session, out.action_id, razorpay=MockRazorpayClient())
    session.commit()

    with pytest.raises(RazorpayError):
        simulate_capture(session, out.action_id, razorpay=_FailingRazorpayClient())
    session.commit()

    # Uncertain outcome -> PENDING_UNRESOLVED, reservation NOT rolled back.
    action = session.get(Action, out.action_id)
    assert action.status == ActionStatus.PENDING_UNRESOLVED

    mandate = session.get(Mandate, "man_A_regular_2k")
    assert mandate.current_period_spend == Decimal("1499.00")
    assert mandate.current_period_transactions == 1


# ---- refund ---------------------------------------------------------------


def test_refund_action_marks_refunded_and_rolls_back_mandate(session):
    _seeded(session)

    out = evaluate_proposal(
        session,
        _proposal(
            mandate_id="man_B_bulk_5k",
            customer_id="cust_bulk_buyer",
            amount=Decimal("1500.00"),
            quoted_price=Decimal("1500.00"),
            current_price=Decimal("1500.00"),
            idempotency_key="idem_refund_1",
        ),
    )
    session.commit()
    execute_payment(session, out.action_id, razorpay=MockRazorpayClient())
    session.commit()
    simulate_capture(session, out.action_id, razorpay=MockRazorpayClient())
    session.commit()

    mandate = session.get(Mandate, "man_B_bulk_5k")
    assert mandate.current_period_spend == Decimal("1500.00")
    assert mandate.current_period_transactions == 1

    result = refund_action(session, out.action_id, razorpay=MockRazorpayClient())
    session.commit()

    assert result.action_status == ActionStatus.REFUNDED
    assert result.refund.razorpay_id.startswith("rfnd_MOCK")

    mandate = session.get(Mandate, "man_B_bulk_5k")
    assert mandate.current_period_spend == Decimal("0")
    assert mandate.current_period_transactions == 0


def test_refund_rejects_non_completed_action(session):
    _seeded(session)
    out = evaluate_proposal(session, _proposal(idempotency_key="idem_refund_wrong"))
    session.commit()
    # ALLOWED state, no payment yet.
    with pytest.raises(InvalidPaymentStateError):
        refund_action(session, out.action_id, razorpay=MockRazorpayClient())
