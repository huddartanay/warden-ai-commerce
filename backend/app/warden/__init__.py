"""
Warden Core — the deterministic authorization boundary.

ARCHITECTURAL RULE: nothing in this package may call an LLM. All financially
sensitive decisions are made here in pure Python. LLM output can inform a
proposal, but must never appear in the decision path.
"""

from app.warden.coordinator import (
    ActionNotFoundError,
    InvalidActionStateError,
    MandateNotFoundError,
    PaymentInvalidStateError,
    PaymentNotFoundError,
    RazorpayError,
    WardenError,
    WardenOutcome,
    approve_step_up,
    evaluate_proposal,
    execute_payment,
    refund_action,
    revoke_mandate,
    simulate_capture,
)
from app.warden.engine import EngineDecision, evaluate
from app.warden.policies import CheckResult, Proposal, WardenConfig

__all__ = [
    "ActionNotFoundError",
    "CheckResult",
    "EngineDecision",
    "InvalidActionStateError",
    "MandateNotFoundError",
    "PaymentInvalidStateError",
    "PaymentNotFoundError",
    "Proposal",
    "RazorpayError",
    "WardenConfig",
    "WardenError",
    "WardenOutcome",
    "approve_step_up",
    "evaluate",
    "evaluate_proposal",
    "execute_payment",
    "refund_action",
    "revoke_mandate",
    "simulate_capture",
]
