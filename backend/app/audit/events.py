"""
Canonical audit event type catalog.

Every audit `append_event` call MUST reference a name from this module. Typos
therefore become ImportErrors, not silently misnamed rows.
"""

from __future__ import annotations

from typing import Final

# ---- Mandate lifecycle ------------------------------------------------------

MANDATE_CREATED: Final[str] = "MANDATE_CREATED"
MANDATE_REVOKED: Final[str] = "MANDATE_REVOKED"

# ---- AI Buyer + cart --------------------------------------------------------

INTENT_RECEIVED: Final[str] = "INTENT_RECEIVED"
CART_CREATED: Final[str] = "CART_CREATED"

# ---- Warden decision --------------------------------------------------------

WARDEN_EVALUATED: Final[str] = "WARDEN_EVALUATED"  # umbrella: every decision
BLOCKED: Final[str] = "BLOCKED"                    # narrow: also fires on BLOCK
STEP_UP_REQUESTED: Final[str] = "STEP_UP_REQUESTED"  # narrow: also fires on STEP_UP
HUMAN_APPROVED: Final[str] = "HUMAN_APPROVED"
DUPLICATE_DETECTED: Final[str] = "DUPLICATE_DETECTED"

# ---- Payment lifecycle ------------------------------------------------------

PAYMENT_CREATED: Final[str] = "PAYMENT_CREATED"           # Razorpay order created
PAYMENT_LINK_CREATED: Final[str] = "PAYMENT_LINK_CREATED"
PAYMENT_LINK_FAILED: Final[str] = "PAYMENT_LINK_FAILED"
PAYMENT_COMPLETED: Final[str] = "PAYMENT_COMPLETED"       # capture succeeded
PAYMENT_FAILED: Final[str] = "PAYMENT_FAILED"
PAYMENT_PENDING_UNRESOLVED: Final[str] = "PAYMENT_PENDING_UNRESOLVED"

# ---- Refund lifecycle -------------------------------------------------------

REFUND_REQUESTED: Final[str] = "REFUND_REQUESTED"
REFUND_COMPLETED: Final[str] = "REFUND_COMPLETED"

# ---- Resolution / system ----------------------------------------------------

RESOLUTION_APPLIED: Final[str] = "RESOLUTION_APPLIED"
SYSTEM_ERROR: Final[str] = "SYSTEM_ERROR"
AGENT_AUTH_FAILED: Final[str] = "AGENT_AUTH_FAILED"


ALL_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        MANDATE_CREATED,
        MANDATE_REVOKED,
        INTENT_RECEIVED,
        CART_CREATED,
        WARDEN_EVALUATED,
        BLOCKED,
        STEP_UP_REQUESTED,
        HUMAN_APPROVED,
        DUPLICATE_DETECTED,
        PAYMENT_CREATED,
        PAYMENT_LINK_CREATED,
        PAYMENT_LINK_FAILED,
        PAYMENT_COMPLETED,
        PAYMENT_FAILED,
        PAYMENT_PENDING_UNRESOLVED,
        REFUND_REQUESTED,
        REFUND_COMPLETED,
        RESOLUTION_APPLIED,
        SYSTEM_ERROR,
        AGENT_AUTH_FAILED,
    }
)
