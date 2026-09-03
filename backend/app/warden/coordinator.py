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

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    # same decision. No new action, no new audit event.
    existing = _load_action_by_idempotency_key(session, proposal.idempotency_key)
    if existing is not None:
        existing_decision = _decision_for_action(session, existing.id)
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

    # Load the mandate. Missing mandate is still an outcome we want recorded
    # so the front-end and audit see the attempt.
    mandate = session.get(Mandate, proposal.mandate_id)

    # Refresh the mandate's computed status before evaluating (so a validity
    # window that has silently elapsed is caught even without a background job).
    if mandate is not None:
        computed = recompute_status(mandate, now=when)
        if computed != mandate.status:
            mandate.status = computed

    engine_result: EngineDecision = evaluate(mandate, proposal, now=when, config=config)

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

    # Reserve budget on ALLOW. STEP_UP defers reservation to approval time.
    if engine_result.result == DecisionResult.ALLOW and mandate is not None:
        apply_successful_action(mandate, amount=Decimal(proposal.amount), now=when)

    # Audit event.
    append_event(
        session,
        event_type="WARDEN_EVALUATED",
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
        event_type="HUMAN_APPROVED",
        action_id=action.id,
        event_data={
            "action_id": action.id,
            "mandate_id": mandate.id,
            "amount": str(Decimal(action.amount)),
            "currency": action.currency,
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
        event_type="MANDATE_REVOKED",
        event_data={
            "mandate_id": mandate.id,
            "customer_id": mandate.customer_id,
            "merchant_id": mandate.merchant_id,
        },
        timestamp=when,
    )
    return mandate


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
