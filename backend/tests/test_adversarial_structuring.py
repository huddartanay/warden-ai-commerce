"""
Stage 7 (3/4) — adversarial agent behavior demo.

A manipulated AI Buyer Agent tries to evade the mandate cap by splitting
one large purchase into several smaller sequential proposals inside a short
window (structuring / smurfing). Warden must catch this via cumulative
spend across a rolling window, with a BLOCK reason specific enough to show
on a judge dashboard.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.audit import events
from app.models import Action, ActionStatus, AuditLog, Mandate
from app.models.enums import ActionType, DecisionResult, ReasonCode
from app.seed import seed_data
from app.warden import Proposal, evaluate_proposal


def _seeded(session):
    seed_data(session)
    session.commit()


def _prop(i: int, amount: Decimal) -> Proposal:
    return Proposal(
        mandate_id="man_B_bulk_5k",
        customer_id="cust_bulk_buyer",
        merchant_id="mer_priya_coffee",
        cart_id=f"cart_struct_{i}",
        amount=amount,
        currency="INR",
        category="coffee",
        quoted_price=amount,
        current_price=amount,
        idempotency_key=f"struct_{i}",
    )


def test_demo_agent_structuring_attack_detected(session):
    """
    Mandate B: generous long-horizon cap of ₹20,000, but a strict rolling
    window of ₹5,000 in any 90-second interval. Step-up disabled so small
    per-transaction amounts flow through the individual checks.

    Attack:
      Instead of one ₹4500 purchase (which would trigger STEP_UP), the
      manipulated agent submits six ₹1000 proposals in quick succession.
      Each is individually well under the mandate cap. The first five ALLOW
      (5 * 1000 = 5000 == rolling cap). The 6th would push the 90-second
      total to ₹6000, tripping the rolling-window structuring check.
    """
    _seeded(session)

    mandate = session.get(Mandate, "man_B_bulk_5k")
    mandate.max_amount = Decimal("20000.00")       # generous long-horizon cap
    mandate.transaction_limit = 100                # so tx_limit isn't the block
    mandate.step_up_over_amount = None             # let small proposals slip past
    mandate.rolling_window_seconds = 90
    mandate.rolling_window_max_amount = Decimal("5000.00")
    session.commit()

    outcomes = []
    for i in range(6):
        out = evaluate_proposal(session, _prop(i, Decimal("1000.00")))
        session.commit()
        outcomes.append(out)

    decisions = [o.decision for o in outcomes]
    reasons = [o.reason_code for o in outcomes]

    # First 5 should ALLOW (5 * 1000 = 5000 == cap). The 6th must BLOCK on
    # cumulative-spend because 6000 > 5000.
    assert decisions[:5] == [DecisionResult.ALLOW] * 5, decisions
    assert decisions[5] == DecisionResult.BLOCK
    assert reasons[5] == ReasonCode.CUMULATIVE_SPEND_EXCEEDED, reasons[5]

    tripping_explanation = outcomes[5].explanation
    # Judge-dashboard-ready detail: names the exact totals + count + window.
    assert "CUMULATIVE_SPEND_EXCEEDED" in tripping_explanation
    assert "90s" in tripping_explanation
    assert "₹5,000.00" in tripping_explanation  # cap
    assert "₹6,000.00" in tripping_explanation  # would-be total

    # Audit trail includes the exact proposal that tripped it.
    tripping_action_id = outcomes[5].action_id
    audit = (
        session.execute(
            select(AuditLog)
            .where(AuditLog.action_id == tripping_action_id)
            .order_by(AuditLog.seq.asc())
        )
        .scalars()
        .all()
    )
    types = [r.event_type for r in audit]
    assert events.WARDEN_EVALUATED in types
    assert events.BLOCKED in types
    # WARDEN_EVALUATED payload names the specific check that failed.
    warden_row = next(r for r in audit if r.event_type == events.WARDEN_EVALUATED)
    check_names = {c["name"]: c for c in warden_row.event_data["checks"]}
    assert check_names["rolling_window_spend"]["ok"] is False
    assert (
        check_names["rolling_window_spend"]["reason_code"]
        == ReasonCode.CUMULATIVE_SPEND_EXCEEDED.value
    )


def test_rolling_window_ignores_activity_outside_the_window(session):
    """
    An older ALLOWED action from before the rolling window opened does NOT
    count against a new proposal. Proves the window really is a WINDOW.
    """
    _seeded(session)
    from datetime import datetime, timezone

    mandate = session.get(Mandate, "man_B_bulk_5k")
    mandate.transaction_limit = 100
    mandate.step_up_over_amount = None
    mandate.rolling_window_seconds = 30  # very short
    session.commit()

    # A stale action 5 minutes ago. Not touching the mandate reservation
    # counters — we're simulating history.
    long_ago = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    session.add(
        Action(
            id="act_stale_1",
            mandate_id=mandate.id,
            cart_id=None,
            action_type=ActionType.PAYMENT,
            amount=Decimal("4000.00"),
            currency="INR",
            idempotency_key="stale_1",
            status=ActionStatus.PAYMENT_COMPLETED,
            created_at=long_ago,
            updated_at=long_ago,
        )
    )
    session.commit()

    out = evaluate_proposal(session, _prop(99, Decimal("1000.00")))
    session.commit()
    # Stale action is outside the 30s window -> rolling check ignores it.
    # The mandate-side spend counter also hasn't been affected by our raw
    # insert, so the amount_within_cap check passes too.
    assert out.decision == DecisionResult.ALLOW
