"""
Push-button demo scenarios for the judge dashboard.

Each scenario runs the FULL stack (agent + Warden + payments + audit) server
side and returns one JSON envelope the frontend needs to render its three
panels + audit trail. This exists so a judge can click one button and see
end-to-end behaviour deterministically; the frontend never fakes anything.

Every scenario uses a fresh idempotency key so it can be re-run in the same
session. `POST /demo/reset` clears prior-run reservation counters on the
seeded mandates so scenarios stay repeatable during a demo.
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.agents import BuyerAgent, MockLLMClient
from app.audit import GENESIS_HASH, verify_chain
from app.db import get_db
from app.models import (
    Action,
    ActionStatus,
    AuditLog,
    Cart,
    Decision,
    Mandate,
    MandateStatus,
    RazorpayRef,
    Resolution,
)
from app.models.enums import DecisionResult, ReasonCode
from app.seed import MERCHANT_ID, seed_data
from app.warden import (
    Proposal,
    RazorpayError,
    evaluate_proposal,
    execute_payment,
    make_demo_failing_capture_client,
    simulate_capture,
)

router = APIRouter(prefix="/demo", tags=["demo"])


# ---- Helpers --------------------------------------------------------------


def _run_key(prefix: str) -> str:
    """Unique idempotency key per demo invocation."""
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


def _reset_mandate_counters(db: Session, mandate_id: str) -> None:
    """
    Zero out the reservation counters on ONE mandate and put it back into
    ACTIVE state, so a demo button that consumes budget can be re-run in
    the same session without needing a full /demo/reset (which would also
    wipe the audit chain).
    """
    db.execute(
        update(Mandate)
        .where(Mandate.id == mandate_id)
        .values(
            current_period_spend=Decimal("0"),
            current_period_transactions=0,
            version=Mandate.version + 1,
            status=MandateStatus.ACTIVE,
        )
    )


def _action_envelope(session: Session, action_id: str) -> dict:
    """Build the JSON the dashboard needs for one action."""
    action = session.get(Action, action_id)
    if action is None:
        return {}
    decision = session.execute(
        select(Decision).where(Decision.action_id == action_id)
    ).scalar_one_or_none()
    refs = (
        session.execute(
            select(RazorpayRef)
            .where(RazorpayRef.action_id == action_id)
            .order_by(RazorpayRef.created_at.asc())
        )
        .scalars()
        .all()
    )
    resolution = session.execute(
        select(Resolution).where(Resolution.action_id == action_id)
    ).scalar_one_or_none()
    # Return the last ~40 audit events GLOBALLY, in chronological order,
    # so events without an action_id (INTENT_RECEIVED, CART_CREATED,
    # MANDATE_CREATED) still appear on the dashboard's audit panel. The
    # per-action detail page still filters strictly by action_id.
    audit_desc = (
        session.execute(
            select(AuditLog).order_by(AuditLog.seq.desc()).limit(40)
        )
        .scalars()
        .all()
    )
    audit = list(reversed(audit_desc))
    cart = session.get(Cart, action.cart_id) if action.cart_id else None
    mandate = session.get(Mandate, action.mandate_id)

    return {
        "action": {
            "id": action.id,
            "mandate_id": action.mandate_id,
            "cart_id": action.cart_id,
            "amount": str(action.amount),
            "currency": action.currency,
            "idempotency_key": action.idempotency_key,
            "status": action.status.value,
            "created_at": action.created_at.isoformat(),
            "updated_at": action.updated_at.isoformat(),
        },
        "decision": (
            {
                "id": decision.id,
                "result": decision.result.value,
                "reason_code": decision.reason_code.value,
                "explanation": decision.explanation,
                "created_at": decision.created_at.isoformat(),
            }
            if decision
            else None
        ),
        "cart": (
            {
                "id": cart.id,
                "items": cart.items,
                "total_amount": str(cart.total_amount),
                "currency": cart.currency,
                "period": cart.period,
            }
            if cart
            else None
        ),
        "mandate": (
            {
                "id": mandate.id,
                "customer_id": mandate.customer_id,
                "max_amount": str(mandate.max_amount),
                "currency": mandate.currency,
                "allowed_categories": list(mandate.allowed_categories or []),
                "transaction_limit": mandate.transaction_limit,
                "status": mandate.status.value,
                "current_period_spend": str(mandate.current_period_spend),
                "current_period_transactions": mandate.current_period_transactions,
                "step_up_over_amount": (
                    str(mandate.step_up_over_amount)
                    if mandate.step_up_over_amount is not None
                    else None
                ),
            }
            if mandate
            else None
        ),
        "razorpay_refs": [
            {
                "id": r.id,
                "ref_type": r.ref_type,
                "razorpay_id": r.razorpay_id,
                "status": r.status,
                "raw_response": r.raw_response,
                "created_at": r.created_at.isoformat(),
            }
            for r in refs
        ],
        "resolution": (
            {
                "status": resolution.status.value,
                "note": resolution.note,
                "resolved_by": resolution.resolved_by,
                "resolved_at": (
                    resolution.resolved_at.isoformat() if resolution.resolved_at else None
                ),
                "updated_at": resolution.updated_at.isoformat(),
            }
            if resolution
            else None
        ),
        "audit": [
            {
                "seq": r.seq,
                "event_id": r.event_id,
                "action_id": r.action_id,
                "event_type": r.event_type,
                "event_data": r.event_data,
                "previous_hash": r.previous_hash,
                "current_hash": r.current_hash,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in audit
        ],
    }


# ---- Reset ----------------------------------------------------------------


@router.post("/reset")
def demo_reset(db: Session = Depends(get_db)) -> dict:
    """
    Return the DB to a clean seeded state:
      - drop every Action, Decision, Cart, RazorpayRef, Resolution row
      - clear all mandate spend / tx counters + version + reset status ACTIVE
      - purge audit_log (chain restarts from GENESIS)
      - re-run seed_data so MANDATE_CREATED events are back on the chain

    Idempotent — safe to run before every demo.
    """
    seed_data(db)
    db.commit()

    db.execute(delete(RazorpayRef))
    db.execute(delete(Resolution))
    db.execute(delete(Decision))
    db.execute(delete(Action))
    db.execute(delete(Cart))
    db.execute(delete(AuditLog))
    db.execute(
        update(Mandate).values(
            current_period_spend=Decimal("0"),
            current_period_transactions=0,
            version=0,
            status=MandateStatus.ACTIVE,
            step_up_over_amount=None,
            rolling_window_seconds=None,
            rolling_window_max_amount=None,
        )
    )
    db.commit()

    # Re-apply the seeded step-up rule for mandate B so the step_up scenario
    # still fires.
    b = db.get(Mandate, "man_B_bulk_5k")
    if b is not None:
        b.step_up_over_amount = Decimal("2000.00")
    db.commit()

    # Re-seed to re-emit MANDATE_CREATED events on the fresh chain.
    seed_data(db)
    db.commit()

    return {"ok": True, "note": "Warden state reset."}


# ---- Scenarios ------------------------------------------------------------


def _scenario_successful_purchase(db: Session) -> dict:
    """AI Buyer purchases coffee under mandate A's cap. ALLOW -> Razorpay order."""
    _reset_mandate_counters(db, "man_A_regular_2k")
    db.commit()

    agent = BuyerAgent(llm=MockLLMClient())
    run = agent.run(
        db,
        natural_language="Restock my coffee. Spend up to ₹2000.",
        customer_id="cust_priya_regular",
        idempotency_key=_run_key("demo_success"),
    )
    db.commit()

    # Auto-execute Razorpay flow on ALLOW so ORDER_CREATED /
    # PAYMENT_LINK_CREATED land in the audit trail, matching what the
    # /agent/purchase-intent endpoint does.
    if run.warden and run.warden.decision == DecisionResult.ALLOW:
        try:
            execute_payment(db, run.warden.action_id)
        except RazorpayError:
            pass
        db.commit()

    envelope = _action_envelope(db, run.warden.action_id) if run.warden else {}
    envelope["scenario"] = "successful_purchase"
    envelope["agent"] = {
        "intent_text": run.intent_text,
        "parsed_intent": run.parsed_intent.to_dict() if run.parsed_intent else None,
        "candidates": [c.to_dict() for c in run.candidates],
        "selected": [s.to_dict() for s in run.selected],
        "confidence": run.agent_confidence,
        "verdict": run.agent_verdict.value,
        "explanation": run.explanation,
    }
    return envelope


def _scenario_cap_exceeded(db: Session) -> dict:
    """
    Direct proposal against mandate C (₹1000 cap) for ₹3499 -> BLOCK
    CAP_EXCEEDED. Uses mandate C (not A) so it stays independent of the
    successful_purchase scenario's mandate A reservation.
    """
    key = _run_key("demo_cap")
    proposal = Proposal(
        mandate_id="man_C_light_1k",
        customer_id="cust_light_user",
        merchant_id=MERCHANT_ID,
        cart_id=f"cart_{key}",
        amount=Decimal("3499.00"),
        currency="INR",
        category="coffee",
        quoted_price=Decimal("3499.00"),
        current_price=Decimal("3499.00"),
        idempotency_key=key,
    )
    outcome = evaluate_proposal(db, proposal)
    db.commit()
    envelope = _action_envelope(db, outcome.action_id)
    envelope["scenario"] = "cap_exceeded"
    envelope["agent"] = None
    return envelope


def _scenario_step_up(db: Session) -> dict:
    """Mandate B: proposal above the ₹2000 step-up threshold -> STEP_UP."""
    key = _run_key("demo_step_up")
    # Make sure the step-up rule is on the mandate (a reset may have cleared it).
    b = db.get(Mandate, "man_B_bulk_5k")
    if b is not None and b.step_up_over_amount is None:
        b.step_up_over_amount = Decimal("2000.00")
        db.commit()
    proposal = Proposal(
        mandate_id="man_B_bulk_5k",
        customer_id="cust_bulk_buyer",
        merchant_id=MERCHANT_ID,
        cart_id=f"cart_{key}",
        amount=Decimal("2500.00"),
        currency="INR",
        category="coffee",
        quoted_price=Decimal("2500.00"),
        current_price=Decimal("2500.00"),
        idempotency_key=key,
    )
    outcome = evaluate_proposal(db, proposal)
    db.commit()
    envelope = _action_envelope(db, outcome.action_id)
    envelope["scenario"] = "step_up"
    envelope["agent"] = None
    return envelope


def _scenario_duplicate(db: Session) -> dict:
    """
    Two identical proposals -> same action_id, second is duplicate.
    Uses mandate B (₹5000 cap, tx_limit=2) so re-runs stay independent of
    mandate A. Resets mandate B first for repeatability.
    """
    _reset_mandate_counters(db, "man_B_bulk_5k")
    db.commit()
    key = _run_key("demo_dup")
    proposal = Proposal(
        mandate_id="man_B_bulk_5k",
        customer_id="cust_bulk_buyer",
        merchant_id=MERCHANT_ID,
        cart_id=f"cart_{key}",
        amount=Decimal("699.00"),
        currency="INR",
        category="coffee",
        quoted_price=Decimal("699.00"),
        current_price=Decimal("699.00"),
        idempotency_key=key,
    )
    first = evaluate_proposal(db, proposal)
    db.commit()
    second = evaluate_proposal(db, proposal)
    db.commit()

    envelope = _action_envelope(db, first.action_id)
    envelope["scenario"] = "duplicate"
    envelope["agent"] = None
    envelope["duplicate_of"] = first.action_id
    envelope["second_call_duplicate_flag"] = second.duplicate
    return envelope


def _scenario_price_drift(db: Session) -> dict:
    """
    Quoted != current beyond tolerance -> BLOCK PRICE_DRIFT.
    Uses mandate C (₹1000 cap) to keep independent of other scenarios.
    """
    key = _run_key("demo_drift")
    proposal = Proposal(
        mandate_id="man_C_light_1k",
        customer_id="cust_light_user",
        merchant_id=MERCHANT_ID,
        cart_id=f"cart_{key}",
        amount=Decimal("699.00"),
        currency="INR",
        category="coffee",
        quoted_price=Decimal("699.00"),
        current_price=Decimal("799.00"),
        idempotency_key=key,
    )
    outcome = evaluate_proposal(db, proposal)
    db.commit()
    envelope = _action_envelope(db, outcome.action_id)
    envelope["scenario"] = "price_drift"
    envelope["agent"] = None
    return envelope


def _scenario_payment_failure(db: Session) -> dict:
    """
    ALLOW -> Razorpay order created -> capture FAILS with uncertain outcome
    -> action PENDING_UNRESOLVED, reservation NOT rolled back, human
    resolution queue populated. Demonstrates safe failure.
    """
    key = _run_key("demo_fail")
    _reset_mandate_counters(db, "man_B_bulk_5k")
    b = db.get(Mandate, "man_B_bulk_5k")
    if b is not None and b.step_up_over_amount is not None:
        # Turn off step-up for this one so the flow reaches capture.
        b.step_up_over_amount = None
    db.commit()

    proposal = Proposal(
        mandate_id="man_B_bulk_5k",
        customer_id="cust_bulk_buyer",
        merchant_id=MERCHANT_ID,
        cart_id=f"cart_{key}",
        amount=Decimal("1499.00"),
        currency="INR",
        category="coffee",
        quoted_price=Decimal("1499.00"),
        current_price=Decimal("1499.00"),
        idempotency_key=key,
    )
    outcome = evaluate_proposal(db, proposal)
    db.commit()

    if outcome.decision == DecisionResult.ALLOW:
        execute_payment(db, outcome.action_id)
        db.commit()
        try:
            simulate_capture(
                db, outcome.action_id, razorpay=make_demo_failing_capture_client()
            )
        except RazorpayError:
            pass
        db.commit()

    envelope = _action_envelope(db, outcome.action_id)
    envelope["scenario"] = "payment_failure"
    envelope["agent"] = None
    return envelope


_SCENARIOS: dict[str, Callable[[Session], dict]] = {
    "successful_purchase": _scenario_successful_purchase,
    "cap_exceeded": _scenario_cap_exceeded,
    "step_up": _scenario_step_up,
    "duplicate": _scenario_duplicate,
    "price_drift": _scenario_price_drift,
    "payment_failure": _scenario_payment_failure,
}


@router.get("/scenarios")
def list_scenarios() -> dict:
    return {"scenarios": sorted(_SCENARIOS.keys())}


@router.post("/scenario/{name}")
def run_scenario(name: str, db: Session = Depends(get_db)) -> dict:
    fn = _SCENARIOS.get(name)
    if fn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown demo scenario {name!r}. Try one of {sorted(_SCENARIOS.keys())}.",
        )
    return fn(db)


# ---- Convenience for the dashboard ----------------------------------------


@router.get("/summary")
def demo_summary(db: Session = Depends(get_db)) -> dict:
    """
    Snapshot for the dashboard header: mandate counts, recent action counts,
    audit chain validity, resolution-queue depth, and KPIs the dashboard
    renders (protected value, allowed / blocked / step_up counts).
    """
    from sqlalchemy import func

    ALLOWED_STATES = {
        ActionStatus.ALLOWED,
        ActionStatus.STEP_UP_APPROVED,
        ActionStatus.PAYMENT_INITIATED,
        ActionStatus.PAYMENT_COMPLETED,
    }
    BLOCKED_STATES = {ActionStatus.BLOCKED, ActionStatus.PAYMENT_FAILED}

    mandate_count = db.scalar(select(func.count()).select_from(Mandate)) or 0
    action_count = db.scalar(select(func.count()).select_from(Action)) or 0
    pending_review = db.scalar(
        select(func.count()).select_from(Resolution).where(
            Resolution.status.in_(["PENDING_UNRESOLVED", "REQUIRES_HUMAN"])
        )
    ) or 0
    audit_count = db.scalar(select(func.count()).select_from(AuditLog)) or 0
    ok, reason = verify_chain(db)

    # Count actions by decision result via the Decision row (definitive).
    result_counts = db.execute(
        select(Decision.result, func.count()).group_by(Decision.result)
    ).all()
    allowed_count = 0
    blocked_count = 0
    step_up_count = 0
    for r, n in result_counts:
        if r == DecisionResult.ALLOW:
            allowed_count = int(n)
        elif r == DecisionResult.BLOCK:
            blocked_count = int(n)
        elif r == DecisionResult.STEP_UP:
            step_up_count = int(n)

    # Protected value = sum of ALLOW'd action amounts. What Warden let AI move.
    allowed_action_ids = db.execute(
        select(Decision.action_id).where(Decision.result == DecisionResult.ALLOW)
    ).scalars().all()
    protected_value = Decimal("0")
    if allowed_action_ids:
        rows = db.execute(
            select(Action.amount).where(Action.id.in_(allowed_action_ids))
        ).all()
        for (amt,) in rows:
            protected_value += Decimal(amt)

    # Blocked value = sum of BLOCK'd action amounts. What Warden refused.
    blocked_action_ids = db.execute(
        select(Decision.action_id).where(Decision.result == DecisionResult.BLOCK)
    ).scalars().all()
    blocked_value = Decimal("0")
    if blocked_action_ids:
        rows = db.execute(
            select(Action.amount).where(Action.id.in_(blocked_action_ids))
        ).all()
        for (amt,) in rows:
            blocked_value += Decimal(amt)

    # Recent transactions for the table.
    recent_rows = (
        db.execute(
            select(Action, Decision)
            .outerjoin(Decision, Decision.action_id == Action.id)
            .order_by(Action.created_at.desc())
            .limit(10)
        )
        .all()
    )
    recent_actions = []
    for a, d in recent_rows:
        ref = db.execute(
            select(RazorpayRef.razorpay_id)
            .where(
                RazorpayRef.action_id == a.id, RazorpayRef.ref_type == "order"
            )
            .limit(1)
        ).scalar_one_or_none()
        recent_actions.append(
            {
                "action_id": a.id,
                "mandate_id": a.mandate_id,
                "amount": str(a.amount),
                "currency": a.currency,
                "status": a.status.value,
                "created_at": a.created_at.isoformat(),
                "decision_result": d.result.value if d else None,
                "reason_code": d.reason_code.value if d else None,
                "razorpay_order_id": ref,
            }
        )

    latest_action = recent_rows[0][0] if recent_rows else None

    return {
        "mandate_count": mandate_count,
        "action_count": action_count,
        "pending_review_count": pending_review,
        "audit_entry_count": audit_count,
        "audit_chain_valid": ok,
        "audit_chain_reason": reason,
        "latest_action_id": latest_action.id if latest_action else None,
        # KPIs
        "allowed_count": allowed_count,
        "blocked_count": blocked_count,
        "step_up_count": step_up_count,
        "protected_value": str(protected_value),
        "blocked_value": str(blocked_value),
        "currency": "INR",
        # Recent activity feed
        "recent_actions": recent_actions,
    }
