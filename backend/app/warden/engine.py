"""
Warden policy engine — orchestrator over the ordered policy checks.

Pure code: no DB, no LLM, no network. Given a mandate, a proposal, and the
current time, returns a deterministic EngineDecision. The caller (coordinator)
is responsible for loading the mandate and persisting the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from app.models.enums import DecisionResult, ReasonCode
from app.models.mandate import Mandate
from app.warden.policies import (
    POLICY_ORDER,
    CheckResult,
    Proposal,
    WardenConfig,
    WardenContext,
    check_mandate_exists,
)


@dataclass(frozen=True)
class EngineDecision:
    result: DecisionResult
    reason_code: ReasonCode
    explanation: str
    checks: list[CheckResult] = field(default_factory=list)


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def evaluate(
    mandate: Mandate | None,
    proposal: Proposal,
    *,
    now: datetime | None = None,
    config: WardenConfig | None = None,
    context: WardenContext | None = None,
) -> EngineDecision:
    """Run the policy chain and produce a single deterministic decision."""
    when = now or _now_utc()
    cfg = config or WardenConfig()
    ctx = context or WardenContext()

    checks: list[CheckResult] = []

    # Step 1: mandate exists. Special-cased because a missing mandate means
    # every downstream check would NPE.
    existence = check_mandate_exists(mandate, proposal, when, cfg, ctx)
    checks.append(existence)
    if not existence.ok:
        return EngineDecision(
            result=DecisionResult.BLOCK,
            reason_code=existence.reason_code or ReasonCode.INVALID_MANDATE,
            explanation=existence.detail,
            checks=checks,
        )

    assert mandate is not None  # for the type-checker; ensured by the check above

    step_up: CheckResult | None = None

    for policy in POLICY_ORDER:
        result = policy(mandate, proposal, when, cfg, ctx)
        checks.append(result)

        if result.verdict == "PASS":
            continue

        if result.verdict == "STEP_UP":
            # Only the step-up rule emits this. Remember it, keep going in
            # case a later policy hard-BLOCKs.
            step_up = result
            continue

        # BLOCK → short-circuit.
        return EngineDecision(
            result=DecisionResult.BLOCK,
            reason_code=result.reason_code or ReasonCode.SYSTEM_ERROR,
            explanation=result.detail,
            checks=checks,
        )

    if step_up is not None:
        return EngineDecision(
            result=DecisionResult.STEP_UP,
            reason_code=step_up.reason_code or ReasonCode.APPROVAL_REQUIRED,
            explanation=step_up.detail,
            checks=checks,
        )

    return EngineDecision(
        result=DecisionResult.ALLOW,
        reason_code=ReasonCode.OK,
        explanation="All Warden checks passed.",
        checks=checks,
    )
