"""
Warden coordinator — DB-facing service.

Responsibilities:
  - resolve idempotency (same key -> same decision, always)
  - load the mandate and refresh its computed status
  - invoke the pure engine
  - persist Action + Decision
  - on ALLOW: reserve budget on the mandate (increment spend + tx counters)
  - append the WARDEN_EVALUATED audit event
  - approve a STEP_UP action (HUMAN_APPROVED, then reserve)
  - revoke a mandate (MANDATE_REVOKED)

The engine stays pure; every side effect happens here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import events
from app.audit.service import append_event
from app.models import (
    Action,
    ActionStatus,
    ActionType,
    Decision,
    Mandate,
    MandateStatus,
    ReasonCode,
)
from app.models.enums import DecisionResult
# The payment layer lives under app.payments; per the architectural invariant,
# ONLY this coordinator may import it. Exception types are re-exported so the
# API layer (which handles HTTP mapping) doesn't need to reach into payments.
from app.payments import (
    InvalidPaymentStateError as PaymentInvalidStateError,
    PaymentActionNotFoundError as PaymentNotFoundError,
    PaymentCapture,
    PaymentExecution,
    PaymentRefund,
    RazorpayError,
    execute_payment as _execute_payment,
    refund_action as _refund_action,
    simulate_capture as _simulate_capture,
)
from app.services.mandate_state import (
    apply_successful_action,
    recompute_status,
    revoke as mandate_revoke,
)
from app.warden.engine import EngineDecision, evaluate
from app.warden.policies import CheckResult, Proposal, WardenConfig


# ---- Public result -----------------------------------------------------------


@dataclass
class WardenOutcome:
    """What the coordinator returns to the API layer."""

    action_id: str
    decision: DecisionResult
    reason_code: ReasonCode
    explanation: str
    checks: list[CheckResult] = field(default_factory=list)
    duplicate: bool = False


# ---- Helpers -----------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


def _load_action_by_idempotency_key(session: Session, key: str) -> Action | None:
    return session.execute(
        select(Action).where(Action.idempotency_key == key)
    ).scalar_one_or_none()


def _decision_for_action(session: Session, action_id: str) -> Decision | None:
    return session.execute(
        select(Decision).where(Decision.action_id == action_id)
    ).scalar_one_or_none()


def _load_action_checks_from_audit(session: Session, action_id: str) -> list[CheckResult]:
    """
    Rebuild a checks list for a cached (idempotent) response by pulling the
    stored payload from the WARDEN_EVALUATED audit event, if present.
    Best-effort; returns [] if unavailable.
    """
    from app.models.audit import AuditLog  # local import to avoid a cycle

    row = session.execute(
        select(AuditLog)
        .where(AuditLog.action_id == action_id, AuditLog.event_type == "WARDEN_EVALUATED")
        .order_by(AuditLog.seq.asc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return []
    checks_raw = (row.event_data or {}).get("checks", [])
    out: list[CheckResult] = []
    for c in checks_raw:
        try:
            reason = ReasonCode(c["reason_code"]) if c.get("reason_code") else None
        except Exception:
            reason = None
        out.append(
            CheckResult(
                name=str(c.get("name", "")),
                ok=bool(c.get("ok", False)),
                verdict=str(c.get("verdict", "PASS")),  # type: ignore[arg-type]
                reason_code=reason,
                detail=str(c.get("detail", "")),
            )
        )
    return out


def _status_from_decision(result: DecisionResult) -> ActionStatus:
    return {
        DecisionResult.ALLOW: ActionStatus.ALLOWED,
        DecisionResult.STEP_UP: ActionStatus.STEP_UP_PENDING,
        DecisionResult.BLOCK: ActionStatus.BLOCKED,
    }[result]


_MAX_CAS_RETRIES = 3


def _try_reserve_cas(
    session: Session,
    *,
    mandate: Mandate,
    amount: Decimal,
    now: datetime | None = None,
) -> bool:
    """
    Atomic compare-and-swap: reserve `amount` against `mandate` only if the
    mandate's version hasn't moved since we read it. Returns True on success.

    All three counters + status + version move in a SINGLE UPDATE, so a
    concurrent reader can never see spend/tx incremented but status stale.

    On success:
      - the in-memory `mandate` object is expired so the next read reflects
        the new values.
    On failure (rowcount != 1):
      - nothing was written; the caller must re-read the mandate and re-run
        the policy chain because another proposal may have consumed budget
        in the meantime.
    """
    observed_version = int(mandate.version or 0)
    new_spend = Decimal(mandate.current_period_spend or 0) + Decimal(amount)
    new_tx = int(mandate.current_period_transactions or 0) + 1

    # Compute what the status must be given the NEW counters, so status
    # transitions atomically alongside the spend/tx bump. We build a
    # scratch object rather than mutating the real one before the UPDATE.
    scratch = Mandate(
        id=mandate.id,
        customer_id=mandate.customer_id,
        merchant_id=mandate.merchant_id,
        max_amount=mandate.max_amount,
        currency=mandate.currency,
        allowed_categories=mandate.allowed_categories,
        transaction_limit=mandate.transaction_limit,
        validity_start=mandate.validity_start,
        validity_end=mandate.validity_end,
        status=mandate.status,
        current_period_spend=new_spend,
        current_period_transactions=new_tx,
        step_up_over_amount=mandate.step_up_over_amount,
        version=observed_version + 1,
        created_at=mandate.created_at,
        updated_at=now or _now_utc(),
    )
    new_status = recompute_status(scratch, now=now)

    result = session.execute(
        update(Mandate)
        .where(Mandate.id == mandate.id, Mandate.version == observed_version)
        .values(
            current_period_spend=new_spend,
            current_period_transactions=new_tx,
            status=new_status,
            version=Mandate.version + 1,
            updated_at=now or _now_utc(),
        )
    )
    if result.rowcount != 1:
        return False

    session.expire(mandate)
    return True


def _serialize_checks(checks: list[CheckResult]) -> list[dict]:
    return [
        {
            "name": c.name,
            "ok": c.ok,
            "verdict": c.verdict,
            "reason_code": c.reason_code.value if c.reason_code else None,
            "detail": c.detail,
        }
        for c in checks
    ]


# ---- Main entry points -------------------------------------------------------


def evaluate_proposal(
    session: Session,
    proposal: Proposal,
    *,
    now: datetime | None = None,
    config: WardenConfig | None = None,
) -> WardenOutcome:
    """Run Warden against a proposal, persist everything, return an outcome."""
    when = now or _now_utc()

    # (Spec check 11) Idempotency short-circuit — same key always maps to the
    # same decision. No new action, no new decision row. We DO emit a
    # DUPLICATE_DETECTED audit event so the trail records the repeat attempt.
    existing = _load_action_by_idempotency_key(session, proposal.idempotency_key)
    if existing is not None:
        existing_decision = _decision_for_action(session, existing.id)
        append_event(
            session,
            event_type=events.DUPLICATE_DETECTED,
            action_id=existing.id,
            event_data={
                "action_id": existing.id,
                "idempotency_key": proposal.idempotency_key,
                "original_decision": (
                    existing_decision.result.value if existing_decision else None
                ),
                "original_reason": (
                    existing_decision.reason_code.value if existing_decision else None
                ),
            },
            timestamp=when,
        )
        if existing_decision is None:
            # Shouldn't happen, but be defensive: treat as system error.
            return WardenOutcome(
                action_id=existing.id,
                decision=DecisionResult.BLOCK,
                reason_code=ReasonCode.SYSTEM_ERROR,
                explanation="Existing action has no recorded decision.",
                duplicate=True,
            )
        return WardenOutcome(
            action_id=existing.id,
            decision=existing_decision.result,
            reason_code=existing_decision.reason_code,
            explanation=existing_decision.explanation,
            checks=_load_action_checks_from_audit(session, existing.id),
            duplicate=True,
        )

    # Decide + reserve loop. On an ALLOW we do an atomic compare-and-swap
    # against the mandate's `version`; if a concurrent proposal has moved it,
    # we re-read the mandate and re-run the engine. Bounded retries so a
    # pathological hot mandate can't loop forever.
    #
    # We DO NOT persist Action / Decision / audit inside the loop — those go
    # in exactly once with whatever decision the last iteration produced.
    mandate: Mandate | None = None
    engine_result: EngineDecision | None = None
    cas_conflicted = False

    for _attempt in range(_MAX_CAS_RETRIES):
        # Ensure we read the freshest row on every retry (the previous iteration
        # may have called session.expire on it).
        session.expire_all()
        mandate = session.get(Mandate, proposal.mandate_id)

        # Refresh the mandate's computed status before evaluating (so a validity
        # window that has silently elapsed is caught without a background job).
        if mandate is not None:
            computed = recompute_status(mandate, now=when)
            if computed != mandate.status:
                mandate.status = computed

        engine_result = evaluate(mandate, proposal, now=when, config=config)

        if engine_result.result != DecisionResult.ALLOW or mandate is None:
            # BLOCK / STEP_UP don't touch the reservation counter; no CAS needed.
            break

        if _try_reserve_cas(
            session, mandate=mandate, amount=Decimal(proposal.amount), now=when
        ):
            # Reservation persisted atomically. Done.
            break

        # CAS lost — someone else moved the mandate. Loop and re-decide.
        cas_conflicted = True

    else:
        # Exhausted retries. Force a BLOCK so nothing double-spends.
        engine_result = EngineDecision(
            result=DecisionResult.BLOCK,
            reason_code=ReasonCode.CONCURRENT_UPDATE,
            explanation=(
                "Mandate contention: could not atomically reserve the requested "
                "amount after "
                f"{_MAX_CAS_RETRIES} retries. Try again."
            ),
            checks=list(engine_result.checks) if engine_result is not None else [],
        )

    action_id = proposal.action_id or _new_id("act")

    # Persist the Action.
    action = Action(
        id=action_id,
        mandate_id=proposal.mandate_id,
        cart_id=proposal.cart_id,
        action_type=ActionType.PAYMENT,
        amount=Decimal(proposal.amount),
        currency=proposal.currency,
        idempotency_key=proposal.idempotency_key,
        status=_status_from_decision(engine_result.result),
        created_at=when,
        updated_at=when,
    )
    session.add(action)
    session.flush()

    # Persist the Decision.
    decision = Decision(
        id=_new_id("dec"),
        action_id=action_id,
        result=engine_result.result,
        reason_code=engine_result.reason_code,
        explanation=engine_result.explanation,
        created_at=when,
    )
    session.add(decision)
    session.flush()

    # Reservation, if any, already happened atomically inside the CAS loop
    # above. STEP_UP still defers reservation to /warden/approve — that path
    # continues to call apply_successful_action directly (single-writer;
    # human-triggered, no meaningful concurrency).

    # Umbrella audit event — every decision.
    append_event(
        session,
        event_type=events.WARDEN_EVALUATED,
        action_id=action_id,
        event_data={
            "action_id": action_id,
            "mandate_id": proposal.mandate_id,
            "customer_id": proposal.customer_id,
            "merchant_id": proposal.merchant_id,
            "cart_id": proposal.cart_id,
            "amount": str(Decimal(proposal.amount)),
            "currency": proposal.currency,
            "category": proposal.category,
            "quoted_price": str(Decimal(proposal.quoted_price)),
            "current_price": str(Decimal(proposal.current_price)),
            "idempotency_key": proposal.idempotency_key,
            "decision": engine_result.result.value,
            "reason_code": engine_result.reason_code.value,
            "explanation": engine_result.explanation,
            "checks": _serialize_checks(engine_result.checks),
        },
        timestamp=when,
    )

    # Narrow follow-up events + resolution-queue plumbing for the UI.
    if engine_result.result == DecisionResult.BLOCK:
        append_event(
            session,
            event_type=events.BLOCKED,
            action_id=action_id,
            event_data={
                "action_id": action_id,
                "reason_code": engine_result.reason_code.value,
                "explanation": engine_result.explanation,
            },
            timestamp=when,
        )
    elif engine_result.result == DecisionResult.STEP_UP:
        append_event(
            session,
            event_type=events.STEP_UP_REQUESTED,
            action_id=action_id,
            event_data={
                "action_id": action_id,
                "reason_code": engine_result.reason_code.value,
                "explanation": engine_result.explanation,
            },
            timestamp=when,
        )
        # Auto-enqueue for human review.
        from app.services.resolution import upsert_resolution
        from app.models.enums import ResolutionStatus
        upsert_resolution(
            session,
            action_id=action_id,
            status=ResolutionStatus.REQUIRES_HUMAN,
            note="Warden STEP_UP: awaiting human approval.",
            when=when,
        )

    return WardenOutcome(
        action_id=action_id,
        decision=engine_result.result,
        reason_code=engine_result.reason_code,
        explanation=engine_result.explanation,
        checks=list(engine_result.checks),
        duplicate=False,
    )


def approve_step_up(
    session: Session, action_id: str, *, now: datetime | None = None
) -> Action:
    """
    Approve a STEP_UP_PENDING action. Reserves budget on the mandate and
    records HUMAN_APPROVED in the audit log.
    """
    when = now or _now_utc()
    action = session.get(Action, action_id)
    if action is None:
        raise ActionNotFoundError(action_id)
    if action.status != ActionStatus.STEP_UP_PENDING:
        raise InvalidActionStateError(
            f"Action {action_id} is {action.status.value}; cannot approve."
        )

    mandate = session.get(Mandate, action.mandate_id)
    if mandate is None:
        raise MandateNotFoundError(action.mandate_id)

    apply_successful_action(mandate, amount=Decimal(action.amount), now=when)
    action.status = ActionStatus.STEP_UP_APPROVED
    action.updated_at = when

    append_event(
        session,
        event_type=events.HUMAN_APPROVED,
        action_id=action.id,
        event_data={
            "action_id": action.id,
            "mandate_id": mandate.id,
            "amount": str(Decimal(action.amount)),
            "currency": action.currency,
        },
        timestamp=when,
    )
    # Clear the REQUIRES_HUMAN entry (if any).
    from app.services.resolution import mark_resolved
    from app.models.enums import ResolutionStatus
    mark_resolved(
        session,
        action_id=action.id,
        note="Human approved via /warden/approve.",
        when=when,
    )
    return action


def resolve_pending_action(
    session: Session,
    action_id: str,
    *,
    new_status: ActionStatus | None,
    note: str,
    resolved_by: str = "human",
    now: datetime | None = None,
) -> Action:
    """
    Human-driven resolution of an action stuck in PENDING_UNRESOLVED.

    Legal transitions:
      PENDING_UNRESOLVED -> PAYMENT_COMPLETED  (human confirmed the payment
                             went through out-of-band; keep the reservation)
      PENDING_UNRESOLVED -> PAYMENT_FAILED     (human confirmed the payment
                             did NOT go through; roll back the reservation)
      PENDING_UNRESOLVED -> REFUNDED           (settled and refunded; roll
                             back the reservation)

    If `new_status` is None, the resolution row is marked RESOLVED but the
    action's own status is left as-is (useful for step-up rejections).
    """
    from app.audit import events
    from app.audit.service import append_event
    from app.models import Mandate
    from app.services.mandate_state import roll_back_reservation
    from app.services.resolution import mark_resolved

    when = now or _now_utc()
    action = session.get(Action, action_id)
    if action is None:
        raise ActionNotFoundError(action_id)

    ROLLBACK_TARGETS = {ActionStatus.PAYMENT_FAILED, ActionStatus.REFUNDED}
    ALLOWED_TARGETS = {
        ActionStatus.PAYMENT_COMPLETED,
        ActionStatus.PAYMENT_FAILED,
        ActionStatus.REFUNDED,
    }

    if new_status is not None:
        if action.status != ActionStatus.PENDING_UNRESOLVED:
            raise InvalidActionStateError(
                f"Action {action_id} is {action.status.value}; "
                "only PENDING_UNRESOLVED actions accept a resolution status change."
            )
        if new_status not in ALLOWED_TARGETS:
            raise InvalidActionStateError(
                f"Resolution target {new_status.value} not allowed. "
                f"Use one of {sorted(s.value for s in ALLOWED_TARGETS)}."
            )
        action.status = new_status
        action.updated_at = when
        if new_status in ROLLBACK_TARGETS:
            mandate = session.get(Mandate, action.mandate_id)
            if mandate is not None:
                roll_back_reservation(
                    mandate, amount=Decimal(action.amount), now=when
                )

    mark_resolved(
        session,
        action_id=action.id,
        resolved_by=resolved_by,
        note=note,
        when=when,
    )
    append_event(
        session,
        event_type=events.RESOLUTION_APPLIED,
        action_id=action.id,
        event_data={
            "action_id": action.id,
            "new_action_status": action.status.value,
            "note": note,
            "resolved_by": resolved_by,
        },
        timestamp=when,
    )
    return action


def revoke_mandate(
    session: Session, mandate_id: str, *, now: datetime | None = None
) -> Mandate:
    """Terminal transition to REVOKED. Records MANDATE_REVOKED in the audit log."""
    when = now or _now_utc()
    mandate = session.get(Mandate, mandate_id)
    if mandate is None:
        raise MandateNotFoundError(mandate_id)
    mandate_revoke(mandate)
    mandate.updated_at = when

    append_event(
        session,
        event_type=events.MANDATE_REVOKED,
        event_data={
            "mandate_id": mandate.id,
            "customer_id": mandate.customer_id,
            "merchant_id": mandate.merchant_id,
        },
        timestamp=when,
    )
    return mandate


# ---- Payment orchestration (thin passthrough to app.payments) --------------


def execute_payment(
    session: Session,
    action_id: str,
    *,
    now: datetime | None = None,
    razorpay=None,  # for tests: inject a client (mock/failing) directly
) -> PaymentExecution:
    """
    Post-authorization payment execution. The only public path from Warden's
    world into the Razorpay adapter. Defensive: the payment service itself
    verifies action state, but calling from anywhere but Warden is banned by
    the architectural-invariant tests.
    """
    return _execute_payment(session, action_id, now=now, razorpay=razorpay)


def simulate_capture(
    session: Session,
    action_id: str,
    *,
    now: datetime | None = None,
    razorpay=None,
) -> PaymentCapture:
    return _simulate_capture(session, action_id, now=now, razorpay=razorpay)


def refund_action(
    session: Session,
    action_id: str,
    *,
    now: datetime | None = None,
    razorpay=None,
) -> PaymentRefund:
    return _refund_action(session, action_id, now=now, razorpay=razorpay)


# ---- Errors -----------------------------------------------------------------


class WardenError(Exception):
    pass


class MandateNotFoundError(WardenError):
    def __init__(self, mandate_id: str) -> None:
        super().__init__(f"Mandate {mandate_id} not found.")
        self.mandate_id = mandate_id


class ActionNotFoundError(WardenError):
    def __init__(self, action_id: str) -> None:
        super().__init__(f"Action {action_id} not found.")
        self.action_id = action_id


class InvalidActionStateError(WardenError):
    pass
