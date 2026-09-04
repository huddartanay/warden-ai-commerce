"""
Warden Core — the deterministic authorization boundary.

ARCHITECTURAL RULE: nothing in this package may call an LLM. All financially
sensitive decisions are made here in pure Python. LLM output can inform a
proposal, but must never appear in the decision path.
"""

from app.warden.auth import (
    AuthResult,
    canonicalize_proposal,
    create_credential,
    new_secret,
    sign_proposal,
    verify_agent_authorized,
)
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
    resolve_pending_action,
    revoke_mandate,
    simulate_capture,
)
from app.warden.engine import EngineDecision, evaluate
from app.warden.policies import CheckResult, Proposal, WardenConfig

__all__ = [
    "ActionNotFoundError",
    "AuthResult",
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
    "canonicalize_proposal",
    "create_credential",
    "evaluate",
    "evaluate_proposal",
    "new_secret",
    "sign_proposal",
    "verify_agent_authorized",
    "execute_payment",
    "refund_action",
    "resolve_pending_action",
    "revoke_mandate",
    "simulate_capture",
]
