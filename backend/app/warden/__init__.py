"""
Warden Core — the deterministic authorization boundary.

ARCHITECTURAL RULE: nothing in this package may call an LLM. All financially
sensitive decisions are made here in pure Python. LLM output can inform a
proposal, but must never appear in the decision path.
"""

def make_demo_failing_capture_client():
    """
    DEMO ONLY. Returns a Razorpay client that behaves like the mock for
    every step except `capture_payment`, which raises RazorpayError to
    exercise the PENDING_UNRESOLVED recovery path in a demo scenario.

    Lives here (in warden/) so app/api/demo.py can invoke it without
    directly importing app.payments — preserving the architectural
    invariant that only warden/ may import payments/.
    """
    from app.payments import MockRazorpayClient, RazorpayError

    class _FailingCapture(MockRazorpayClient):
        def capture_payment(self, payment_id, *, amount_paise, currency="INR"):
            raise RazorpayError(
                "Simulated Razorpay capture failure (demo scenario)"
            )

    return _FailingCapture()


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
    "make_demo_failing_capture_client",
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
