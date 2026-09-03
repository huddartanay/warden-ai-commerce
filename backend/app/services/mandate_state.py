"""
Deterministic mandate state machine.

Priority (highest first):

  REVOKED         terminal, sticky. Once revoked, always revoked.
  EXPIRED         validity_end has passed.
  EXHAUSTED       cap or transaction_limit reached.
  PARTIALLY_USED  cap not reached but some spend/transactions have occurred.
  ACTIVE          fresh mandate inside its validity window.

Pure function — no session, no I/O. `recompute_status` reads a Mandate and
returns what its status *should* be. `refresh_status` writes it back on the row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.models.enums import MandateStatus
from app.models.mandate import Mandate


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """SQLite drops timezone metadata on round-trip; treat naive datetimes as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _as_decimal(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def recompute_status(mandate: Mandate, *, now: datetime | None = None) -> MandateStatus:
    """Return the status the mandate should have right now. Never mutates."""
    if mandate.status == MandateStatus.REVOKED:
        return MandateStatus.REVOKED

    when = _ensure_utc(now) or _now_utc()
    end = _ensure_utc(mandate.validity_end)

    if end is not None and when > end:
        return MandateStatus.EXPIRED

    spend = _as_decimal(mandate.current_period_spend or 0)
    cap = _as_decimal(mandate.max_amount)
    used_tx = int(mandate.current_period_transactions or 0)
    tx_limit = int(mandate.transaction_limit)

    if spend >= cap or used_tx >= tx_limit:
        return MandateStatus.EXHAUSTED

    if spend > 0 or used_tx > 0:
        return MandateStatus.PARTIALLY_USED

    return MandateStatus.ACTIVE


def refresh_status(mandate: Mandate, *, now: datetime | None = None) -> MandateStatus:
    """Recompute and write status back on the row. Returns the new status."""
    new_status = recompute_status(mandate, now=now)
    mandate.status = new_status
    return new_status


def revoke(mandate: Mandate) -> None:
    """Terminal transition to REVOKED."""
    mandate.status = MandateStatus.REVOKED


def apply_successful_action(
    mandate: Mandate,
    *,
    amount: Decimal,
    now: datetime | None = None,
) -> MandateStatus:
    """
    Record a successful payment against the mandate: increment spend and
    transaction counters, then recompute status.
    """
    mandate.current_period_spend = _as_decimal(mandate.current_period_spend or 0) + _as_decimal(amount)
    mandate.current_period_transactions = int(mandate.current_period_transactions or 0) + 1
    return refresh_status(mandate, now=now)
