"""
Razorpay client abstraction.

- `RazorpayClient` protocol: create_order, create_payment_link, fetch_payment,
  capture_payment, refund_payment.
- `LiveRazorpayClient` wraps the official SDK. Refuses `rzp_live_` keys —
  Warden's Stage-5 mandate is TEST MODE ONLY.
- `MockRazorpayClient` returns deterministic fake responses so tests + demos
  never depend on network.
- `get_razorpay_client()` picks by RAZORPAY_MODE.
- `RazorpayError` is the single exception type callers catch. `RazorpayRetryable`
  is a subclass for network / 5xx errors that fetch_payment may retry.

Amounts on these methods are ALWAYS integer paise (Razorpay's boundary
convention). Convert with app.payments.money.rupees_to_paise.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Callable, Protocol

from app.config import get_settings


# ---- Errors ----------------------------------------------------------------


class RazorpayError(Exception):
    """All Razorpay-facing failures raise this. Subclasses distinguish retry."""

    def __init__(self, message: str, *, is_retryable: bool = False, raw: Any = None) -> None:
        super().__init__(message)
        self.is_retryable = is_retryable
        self.raw = raw


class RazorpayRetryable(RazorpayError):
    def __init__(self, message: str, *, raw: Any = None) -> None:
        super().__init__(message, is_retryable=True, raw=raw)


# ---- Contract --------------------------------------------------------------


class RazorpayClient(Protocol):
    def create_order(
        self,
        *,
        amount_paise: int,
        currency: str,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    def create_payment_link(
        self,
        *,
        amount_paise: int,
        currency: str,
        reference_id: str,
        description: str,
        notes: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    def fetch_payment(self, payment_id: str) -> dict[str, Any]: ...

    def capture_payment(
        self, payment_id: str, *, amount_paise: int, currency: str = "INR"
    ) -> dict[str, Any]: ...

    def refund_payment(
        self, payment_id: str, *, amount_paise: int | None = None, notes: dict[str, str] | None = None
    ) -> dict[str, Any]: ...


# ---- Live: wraps the razorpay SDK ------------------------------------------


class LiveRazorpayClient:
    """Thin adapter around `razorpay.Client`. Refuses production keys."""

    def __init__(self, *, key_id: str, key_secret: str) -> None:
        if not key_id or not key_secret:
            raise RazorpayError("Razorpay live mode requested but keys are missing.")
        if key_id.startswith("rzp_live_"):
            raise RazorpayError(
                "Refusing to initialize Razorpay client with a production key "
                f"({key_id[:12]}...). Warden Stage 5 is TEST MODE ONLY. "
                "Use an rzp_test_ key."
            )
        # Lazy-import so the SDK is only a runtime dep when live.
        import razorpay

        self._client = razorpay.Client(auth=(key_id, key_secret))

    # --- write path --------------------------------------------------------

    def create_order(self, *, amount_paise, currency, receipt, notes=None):
        try:
            return self._client.order.create(
                data={
                    "amount": int(amount_paise),
                    "currency": currency,
                    "receipt": receipt,
                    "notes": notes or {},
                }
            )
        except Exception as e:
            raise _wrap(e, "create_order failed")

    def create_payment_link(
        self, *, amount_paise, currency, reference_id, description, notes=None
    ):
        try:
            return self._client.payment_link.create(
                {
                    "amount": int(amount_paise),
                    "currency": currency,
                    "reference_id": reference_id,
                    "description": description,
                    "notes": notes or {},
                }
            )
        except Exception as e:
            raise _wrap(e, "create_payment_link failed")

    def capture_payment(self, payment_id, *, amount_paise, currency="INR"):
        try:
            return self._client.payment.capture(
                payment_id, int(amount_paise), {"currency": currency}
            )
        except Exception as e:
            raise _wrap(e, f"capture_payment({payment_id}) failed")

    def refund_payment(self, payment_id, *, amount_paise=None, notes=None):
        try:
            data: dict[str, Any] = {}
            if amount_paise is not None:
                data["amount"] = int(amount_paise)
            if notes:
                data["notes"] = notes
            return self._client.payment.refund(payment_id, data)
        except Exception as e:
            raise _wrap(e, f"refund_payment({payment_id}) failed")

    # --- read path (retryable) ---------------------------------------------

    def fetch_payment(self, payment_id):
        try:
            return self._client.payment.fetch(payment_id)
        except Exception as e:
            raise _wrap(e, f"fetch_payment({payment_id}) failed", retryable=True)


def _wrap(exc: Exception, message: str, *, retryable: bool = False) -> RazorpayError:
    """Normalize any SDK/network error into RazorpayError(Retryable)."""
    cls = RazorpayRetryable if retryable else RazorpayError
    return cls(f"{message}: {type(exc).__name__}: {exc}", raw=exc)


# ---- Mock: deterministic, no network ---------------------------------------


class MockRazorpayClient:
    """
    Deterministic Razorpay mock.

    - IDs are derived from a stable hash of the receipt / payment_id so
      calling the same "endpoint" twice yields identical responses.
    - Payments are auto-captured (test-mode-happy-path). To exercise the
      failure branch, use `FailingRazorpayClient` from the tests.
    """

    def _oid(self, prefix: str, seed: str) -> str:
        h = hashlib.sha256(seed.encode()).hexdigest()
        return f"{prefix}_MOCK{h[:20]}"

    def create_order(self, *, amount_paise, currency, receipt, notes=None):
        return {
            "id": self._oid("order", f"order:{receipt}"),
            "entity": "order",
            "amount": int(amount_paise),
            "amount_paid": 0,
            "amount_due": int(amount_paise),
            "currency": currency,
            "receipt": receipt,
            "status": "created",
            "attempts": 0,
            "notes": notes or {},
            "created_at": int(time.time()),
            "_mock": True,
        }

    def create_payment_link(
        self, *, amount_paise, currency, reference_id, description, notes=None
    ):
        link_id = self._oid("plink", f"plink:{reference_id}")
        return {
            "id": link_id,
            "entity": "payment_link",
            "amount": int(amount_paise),
            "currency": currency,
            "reference_id": reference_id,
            "description": description,
            "short_url": f"https://rzp.io/i/mock/{link_id[-8:]}",
            "status": "created",
            "notes": notes or {},
            "_mock": True,
        }

    def fetch_payment(self, payment_id):
        return {
            "id": payment_id,
            "entity": "payment",
            "status": "captured",
            "amount": 0,  # unknown in mock; caller uses its own record
            "currency": "INR",
            "_mock": True,
        }

    def capture_payment(self, payment_id, *, amount_paise, currency="INR"):
        return {
            "id": payment_id,
            "entity": "payment",
            "status": "captured",
            "amount": int(amount_paise),
            "currency": currency,
            "captured": True,
            "_mock": True,
        }

    def refund_payment(self, payment_id, *, amount_paise=None, notes=None):
        return {
            "id": self._oid("rfnd", f"rfnd:{payment_id}"),
            "entity": "refund",
            "payment_id": payment_id,
            "amount": int(amount_paise) if amount_paise is not None else 0,
            "currency": "INR",
            "status": "processed",
            "notes": notes or {},
            "_mock": True,
        }


# ---- Factory ---------------------------------------------------------------


def get_razorpay_client() -> RazorpayClient:
    settings = get_settings()
    mode = (settings.razorpay_mode or "auto").lower()

    if mode == "mock":
        return MockRazorpayClient()

    if mode == "live":
        return LiveRazorpayClient(
            key_id=settings.razorpay_key_id,
            key_secret=settings.razorpay_key_secret,
        )

    # auto
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        return LiveRazorpayClient(
            key_id=settings.razorpay_key_id,
            key_secret=settings.razorpay_key_secret,
        )
    return MockRazorpayClient()


# ---- Bounded retry helper (read only) --------------------------------------


def retry_read(
    fn: Callable[[], Any],
    *,
    tries: int = 3,
    base_delay_s: float = 0.2,
    max_delay_s: float = 2.0,
) -> Any:
    """
    Run `fn` up to `tries` times. Retries ONLY on RazorpayRetryable.
    Never call this with a write-path function.
    """
    last: Exception | None = None
    delay = base_delay_s
    for attempt in range(tries):
        try:
            return fn()
        except RazorpayRetryable as e:
            last = e
            if attempt == tries - 1:
                break
            time.sleep(min(delay, max_delay_s))
            delay *= 2
    assert last is not None
    raise last
