"""
Razorpay Test-Mode adapter.

ARCHITECTURAL RULE: this package is the ONLY place in the codebase that
imports the razorpay SDK. It is called strictly from app.warden.coordinator,
never from routes, agents, or the API layer. That rule is enforced by
tests/test_architectural_invariants.py.
"""

from app.payments.client import (
    LiveRazorpayClient,
    MockRazorpayClient,
    RazorpayClient,
    RazorpayError,
    RazorpayRetryable,
    get_razorpay_client,
    retry_read,
)
from app.payments.money import paise_to_rupees, rupees_to_paise
from app.payments.service import (
    InvalidPaymentStateError,
    PaymentActionNotFoundError,
    PaymentCapture,
    PaymentExecution,
    PaymentRefund,
    execute_payment,
    fetch_payment_status,
    refund_action,
    simulate_capture,
)

__all__ = [
    "InvalidPaymentStateError",
    "LiveRazorpayClient",
    "MockRazorpayClient",
    "PaymentActionNotFoundError",
    "PaymentCapture",
    "PaymentExecution",
    "PaymentRefund",
    "RazorpayClient",
    "RazorpayError",
    "RazorpayRetryable",
    "execute_payment",
    "fetch_payment_status",
    "get_razorpay_client",
    "paise_to_rupees",
    "refund_action",
    "retry_read",
    "rupees_to_paise",
    "simulate_capture",
]
