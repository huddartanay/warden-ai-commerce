"""
Payment service — DB-facing layer over the Razorpay client.

Only `app.warden.coordinator` may import this module. That is enforced by an
architectural-invariant test. This module never imports the agents package,
never invokes an LLM, and never makes a Warden authorization decision.

Every function here:
  1. Verifies the Action is in the correct state (defensively — Warden ALLOWed
     it in the first place).
  2. Idempotently creates or fetches a RazorpayRef.
  3. Updates action.status via the payment state machine.
  4. Emits a WARDEN-style audit event so the hash chain covers the entire
     lifecycle.
  5. Rolls back the mandate reservation on failure / refund.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import append_event
from app.models import Action, ActionStatus, Mandate, RazorpayRef
from app.payments.client import (
    RazorpayClient,
    RazorpayError,
    get_razorpay_client,
    retry_read,
)
from app.payments.money import rupees_to_paise
from app.services.mandate_state import roll_back_reservation


# ---- Errors ---------------------------------------------------------------


class PaymentActionNotFoundError(Exception):
    pass


class InvalidPaymentStateError(Exception):
    pass


# ---- Public results -------------------------------------------------------


@dataclass
class PaymentExecution:
    action_id: str
    action_status: ActionStatus
    order: RazorpayRef | None
    payment_link: RazorpayRef | None
    duplicate: bool = False


@dataclass
class PaymentCapture:
    action_id: str
    action_status: ActionStatus
    payment: RazorpayRef


@dataclass
class PaymentRefund:
    action_id: str
    action_status: ActionStatus
    refund: RazorpayRef


# ---- Helpers --------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _new_ref_id() -> str:
    return f"rzp_{uuid4().hex[:20]}"


def _find_ref(session: Session, *, action_id: str, ref_type: str) -> RazorpayRef | None:
    return session.execute(
        select(RazorpayRef).where(
            RazorpayRef.action_id == action_id, RazorpayRef.ref_type == ref_type
        )
    ).scalar_one_or_none()


# ---- Post-ALLOW: create order + payment link ------------------------------


def execute_payment(
    session: Session,
    action_id: str,
    *,
    razorpay: RazorpayClient | None = None,
    now: datetime | None = None,
) -> PaymentExecution:
    """
    Called strictly after Warden ALLOW (or STEP_UP_APPROVED). Creates a
    Razorpay order + payment link, records references, moves the action to
    PAYMENT_INITIATED. Idempotent — a second call with an order already
    recorded returns the existing refs without a new Razorpay call.
    """
    when = now or _now_utc()
    action = session.get(Action, action_id)
    if action is None:
        raise PaymentActionNotFoundError(f"Action {action_id} not found.")

    # Legal states to enter payment execution.
    if action.status not in (
        ActionStatus.ALLOWED,
        ActionStatus.STEP_UP_APPROVED,
        # PAYMENT_INITIATED here means we've been here before -> idempotent branch.
        ActionStatus.PAYMENT_INITIATED,
    ):
        raise InvalidPaymentStateError(
            f"Action {action_id} is {action.status.value}; "
            "cannot execute payment. Warden must ALLOW first."
        )

    # Idempotency: reuse the previously created order + link if any.
    existing_order = _find_ref(session, action_id=action_id, ref_type="order")
    if existing_order is not None:
        existing_link = _find_ref(session, action_id=action_id, ref_type="payment_link")
        return PaymentExecution(
            action_id=action.id,
            action_status=action.status,
            order=existing_order,
            payment_link=existing_link,
            duplicate=True,
        )

    rz = razorpay or get_razorpay_client()
    amount_paise = rupees_to_paise(action.amount)

    # -- create_order (never retried) --
    try:
        order_resp = rz.create_order(
            amount_paise=amount_paise,
            currency=action.currency,
            receipt=action.idempotency_key,
            notes={
                "action_id": action.id,
                "mandate_id": action.mandate_id,
                "warden": "true",
            },
        )
    except RazorpayError as e:
        _handle_payment_write_failure(
            session,
            action=action,
            when=when,
            step="create_order",
            error=e,
        )
        raise

    order_ref = RazorpayRef(
        id=_new_ref_id(),
        action_id=action.id,
        ref_type="order",
        razorpay_id=order_resp["id"],
        status=order_resp.get("status"),
        raw_response=order_resp,
        created_at=when,
        updated_at=when,
    )
    session.add(order_ref)
    session.flush()

    append_event(
        session,
        event_type="ORDER_CREATED",
        action_id=action.id,
        event_data={
            "action_id": action.id,
            "razorpay_order_id": order_resp["id"],
            "amount_paise": amount_paise,
            "currency": action.currency,
            "receipt": action.idempotency_key,
        },
        timestamp=when,
    )

    # -- create_payment_link (also never retried; but a failure here is not
    #    catastrophic — the order still exists and can be paid separately). --
    link_ref: RazorpayRef | None = None
    try:
        link_resp = rz.create_payment_link(
            amount_paise=amount_paise,
            currency=action.currency,
            reference_id=action.id,
            description=f"Warden action {action.id}",
            notes={"action_id": action.id, "mandate_id": action.mandate_id},
        )
        link_ref = RazorpayRef(
            id=_new_ref_id(),
            action_id=action.id,
            ref_type="payment_link",
            razorpay_id=link_resp["id"],
            status=link_resp.get("status"),
            raw_response=link_resp,
            created_at=when,
            updated_at=when,
        )
        session.add(link_ref)
        session.flush()
        append_event(
            session,
            event_type="PAYMENT_LINK_CREATED",
            action_id=action.id,
            event_data={
                "action_id": action.id,
                "razorpay_payment_link_id": link_resp["id"],
                "short_url": link_resp.get("short_url"),
            },
            timestamp=when,
        )
    except RazorpayError as e:
        # We still have a valid order; log and continue.
        append_event(
            session,
            event_type="PAYMENT_LINK_FAILED",
            action_id=action.id,
            event_data={
                "action_id": action.id,
                "razorpay_order_id": order_resp["id"],
                "error": str(e),
            },
            timestamp=when,
        )

    action.status = ActionStatus.PAYMENT_INITIATED
    action.updated_at = when

    return PaymentExecution(
        action_id=action.id,
        action_status=action.status,
        order=order_ref,
        payment_link=link_ref,
        duplicate=False,
    )


# ---- Simulate a capture (test-mode demo path) -----------------------------


def simulate_capture(
    session: Session,
    action_id: str,
    *,
    razorpay: RazorpayClient | None = None,
    now: datetime | None = None,
) -> PaymentCapture:
    """
    Skip the client-side checkout dance. In mock mode this immediately marks
    the action PAYMENT_COMPLETED. In live TEST-mode this calls
    Razorpay.capture_payment on a synthetic payment id derived from the order
    receipt so demos never require a browser session.

    Never retried automatically. If Razorpay says the payment can't be
    captured (already captured, missing, refused), we surface the error;
    the action stays PAYMENT_INITIATED for a human to resolve.
    """
    when = now or _now_utc()
    action = session.get(Action, action_id)
    if action is None:
        raise PaymentActionNotFoundError(f"Action {action_id} not found.")
    if action.status != ActionStatus.PAYMENT_INITIATED:
        raise InvalidPaymentStateError(
            f"Action {action_id} is {action.status.value}; "
            "cannot simulate capture. Expected PAYMENT_INITIATED."
        )

    order_ref = _find_ref(session, action_id=action_id, ref_type="order")
    if order_ref is None:
        raise InvalidPaymentStateError(
            f"Action {action_id} has no Razorpay order to capture against."
        )

    rz = razorpay or get_razorpay_client()
    amount_paise = rupees_to_paise(action.amount)

    # Deterministic synthetic payment id keyed on the order id.
    synthetic_payment_id = f"pay_MOCK{order_ref.razorpay_id[-16:]}"

    try:
        capture_resp = rz.capture_payment(
            synthetic_payment_id, amount_paise=amount_paise, currency=action.currency
        )
    except RazorpayError as e:
        # Do NOT roll back yet — we don't know whether the capture happened
        # server-side. Leave for a human to reconcile.
        _mark_pending_unresolved(
            session, action=action, when=when, step="capture_payment", error=e
        )
        raise

    payment_ref = RazorpayRef(
        id=_new_ref_id(),
        action_id=action.id,
        ref_type="payment",
        razorpay_id=capture_resp.get("id", synthetic_payment_id),
        status=capture_resp.get("status", "captured"),
        raw_response=capture_resp,
        created_at=when,
        updated_at=when,
    )
    session.add(payment_ref)
    session.flush()

    action.status = ActionStatus.PAYMENT_COMPLETED
    action.updated_at = when

    append_event(
        session,
        event_type="PAYMENT_CAPTURED",
        action_id=action.id,
        event_data={
            "action_id": action.id,
            "razorpay_payment_id": payment_ref.razorpay_id,
            "amount_paise": amount_paise,
            "currency": action.currency,
        },
        timestamp=when,
    )

    return PaymentCapture(
        action_id=action.id, action_status=action.status, payment=payment_ref
    )


# ---- Refund a captured payment --------------------------------------------


def refund_action(
    session: Session,
    action_id: str,
    *,
    razorpay: RazorpayClient | None = None,
    now: datetime | None = None,
) -> PaymentRefund:
    """
    Refund a PAYMENT_COMPLETED action. Rolls back the mandate reservation on
    success. Never retries automatically.
    """
    when = now or _now_utc()
    action = session.get(Action, action_id)
    if action is None:
        raise PaymentActionNotFoundError(f"Action {action_id} not found.")
    if action.status != ActionStatus.PAYMENT_COMPLETED:
        raise InvalidPaymentStateError(
            f"Action {action_id} is {action.status.value}; "
            "only PAYMENT_COMPLETED actions can be refunded."
        )

    payment_ref = _find_ref(session, action_id=action_id, ref_type="payment")
    if payment_ref is None:
        raise InvalidPaymentStateError(
            f"Action {action_id} has no captured Razorpay payment to refund."
        )

    rz = razorpay or get_razorpay_client()
    amount_paise = rupees_to_paise(action.amount)

    try:
        refund_resp = rz.refund_payment(
            payment_ref.razorpay_id,
            amount_paise=amount_paise,
            notes={"action_id": action.id, "mandate_id": action.mandate_id},
        )
    except RazorpayError as e:
        _mark_pending_unresolved(
            session, action=action, when=when, step="refund_payment", error=e
        )
        raise

    refund_ref = RazorpayRef(
        id=_new_ref_id(),
        action_id=action.id,
        ref_type="refund",
        razorpay_id=refund_resp["id"],
        status=refund_resp.get("status"),
        raw_response=refund_resp,
        created_at=when,
        updated_at=when,
    )
    session.add(refund_ref)
    session.flush()

    action.status = ActionStatus.REFUNDED
    action.updated_at = when

    # Roll back the mandate's spend/tx counters so the customer isn't
    # permanently debited against their cap for a refunded transaction.
    mandate = session.get(Mandate, action.mandate_id)
    if mandate is not None:
        roll_back_reservation(mandate, amount=Decimal(action.amount), now=when)

    append_event(
        session,
        event_type="REFUND_COMPLETED",
        action_id=action.id,
        event_data={
            "action_id": action.id,
            "razorpay_refund_id": refund_resp["id"],
            "razorpay_payment_id": payment_ref.razorpay_id,
            "amount_paise": amount_paise,
        },
        timestamp=when,
    )

    return PaymentRefund(
        action_id=action.id, action_status=action.status, refund=refund_ref
    )


# ---- Read path (fetch_payment with bounded retry) -------------------------


def fetch_payment_status(
    session: Session,
    action_id: str,
    *,
    razorpay: RazorpayClient | None = None,
) -> dict[str, Any]:
    """Bounded-retry read. Returns the raw payment payload."""
    action = session.get(Action, action_id)
    if action is None:
        raise PaymentActionNotFoundError(f"Action {action_id} not found.")
    payment_ref = _find_ref(session, action_id=action_id, ref_type="payment")
    if payment_ref is None:
        raise InvalidPaymentStateError(
            f"Action {action_id} has no payment to fetch."
        )
    rz = razorpay or get_razorpay_client()
    return retry_read(lambda: rz.fetch_payment(payment_ref.razorpay_id))


# ---- Failure paths --------------------------------------------------------


def _handle_payment_write_failure(
    session: Session,
    *,
    action: Action,
    when: datetime,
    step: str,
    error: RazorpayError,
) -> None:
    """
    A write-path Razorpay call failed. We don't know whether Razorpay saw the
    request or not, so we must NOT auto-retry. Roll back the mandate
    reservation (Warden had reserved it on ALLOW) and mark the action FAILED.
    Audit records the failure.
    """
    action.status = ActionStatus.PAYMENT_FAILED
    action.updated_at = when

    mandate = session.get(Mandate, action.mandate_id)
    if mandate is not None:
        roll_back_reservation(mandate, amount=Decimal(action.amount), now=when)

    append_event(
        session,
        event_type="PAYMENT_FAILED",
        action_id=action.id,
        event_data={
            "action_id": action.id,
            "step": step,
            "error": str(error),
            "is_retryable": error.is_retryable,
        },
        timestamp=when,
    )


def _mark_pending_unresolved(
    session: Session,
    *,
    action: Action,
    when: datetime,
    step: str,
    error: RazorpayError,
) -> None:
    """
    A payment operation whose outcome is UNCERTAIN (capture / refund) failed.
    We don't roll back the reservation — a human must reconcile. Audit logs it.
    """
    action.status = ActionStatus.PENDING_UNRESOLVED
    action.updated_at = when
    append_event(
        session,
        event_type="PAYMENT_PENDING_UNRESOLVED",
        action_id=action.id,
        event_data={
            "action_id": action.id,
            "step": step,
            "error": str(error),
        },
        timestamp=when,
    )
