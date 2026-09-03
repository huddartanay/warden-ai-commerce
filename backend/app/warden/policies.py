"""
Deterministic policy check functions.

Each check is a pure function of (Mandate, Proposal, now, config) and returns a
CheckResult. No DB, no LLM, no network. Order of application is defined in
`engine.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Literal

from app.models.enums import MandateStatus, ReasonCode
from app.models.mandate import Mandate

Verdict = Literal["PASS", "STEP_UP", "BLOCK"]


# ---- Types ------------------------------------------------------------------


@dataclass(frozen=True)
class Proposal:
    """The typed payment proposal Warden evaluates."""

    mandate_id: str
    customer_id: str
    merchant_id: str
    cart_id: str
    amount: Decimal
    currency: str
    category: str
    quoted_price: Decimal
    current_price: Decimal
    idempotency_key: str
    action_id: str | None = None


@dataclass(frozen=True)
class WardenConfig:
    """Tunable knobs for Warden. Kept alongside checks so tests can override them."""

    price_drift_tolerance: Decimal = Decimal("0.01")  # 1%


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    verdict: Verdict
    reason_code: ReasonCode | None
    detail: str


def _fmt_money(amount: Decimal, currency: str = "INR") -> str:
    symbol = "₹" if currency == "INR" else f"{currency} "
    return f"{symbol}{amount:,.2f}"


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tz metadata on round-trip; treat naive datetimes as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ---- Individual policies ----------------------------------------------------


def check_mandate_exists(mandate: Mandate | None, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    if mandate is None:
        return CheckResult(
            name="mandate_exists",
            ok=False,
            verdict="BLOCK",
            reason_code=ReasonCode.INVALID_MANDATE,
            detail=f"No mandate with id {proposal.mandate_id}.",
        )
    return CheckResult("mandate_exists", True, "PASS", None, f"mandate {mandate.id} found")


def check_mandate_status(mandate: Mandate, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    if mandate.status == MandateStatus.REVOKED:
        return CheckResult(
            "mandate_status", False, "BLOCK", ReasonCode.MANDATE_REVOKED,
            f"Mandate {mandate.id} has been revoked.",
        )
    if mandate.status == MandateStatus.EXPIRED:
        return CheckResult(
            "mandate_status", False, "BLOCK", ReasonCode.MANDATE_EXPIRED,
            f"Mandate {mandate.id} is expired.",
        )
    if mandate.status == MandateStatus.EXHAUSTED:
        # Exhausted covers both cap-reached and tx-limit-reached; pick the more
        # informative reason based on which counter is at its limit.
        if int(mandate.current_period_transactions or 0) >= int(mandate.transaction_limit):
            return CheckResult(
                "mandate_status", False, "BLOCK", ReasonCode.WINDOW_EXHAUSTED,
                f"Mandate {mandate.id} has used its transaction window "
                f"({mandate.transaction_limit} transactions).",
            )
        return CheckResult(
            "mandate_status", False, "BLOCK", ReasonCode.CAP_EXCEEDED,
            f"Mandate {mandate.id} has exhausted its spending cap.",
        )
    if mandate.status not in (MandateStatus.ACTIVE, MandateStatus.PARTIALLY_USED):
        return CheckResult(
            "mandate_status", False, "BLOCK", ReasonCode.INVALID_MANDATE,
            f"Mandate {mandate.id} has unusable status {mandate.status.value}.",
        )
    return CheckResult("mandate_status", True, "PASS", None, f"status={mandate.status.value}")


def check_within_validity(mandate: Mandate, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    when = _ensure_utc(now) or datetime.now(tz=timezone.utc)
    start = _ensure_utc(mandate.validity_start)
    end = _ensure_utc(mandate.validity_end)

    if start is not None and when < start:
        return CheckResult(
            "within_validity", False, "BLOCK", ReasonCode.INVALID_MANDATE,
            f"Mandate {mandate.id} is not yet valid "
            f"(starts {start.isoformat()}).",
        )
    if end is not None and when > end:
        return CheckResult(
            "within_validity", False, "BLOCK", ReasonCode.MANDATE_EXPIRED,
            f"Mandate {mandate.id} expired on {end.isoformat()}.",
        )
    return CheckResult(
        "within_validity", True, "PASS", None,
        f"inside window until {end.isoformat() if end else 'forever'}",
    )


def check_merchant_match(mandate: Mandate, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    if proposal.merchant_id != mandate.merchant_id:
        return CheckResult(
            "merchant_match", False, "BLOCK", ReasonCode.INVALID_MANDATE,
            f"Proposal merchant {proposal.merchant_id!r} does not match "
            f"mandate merchant {mandate.merchant_id!r}.",
        )
    return CheckResult("merchant_match", True, "PASS", None, f"merchant={mandate.merchant_id}")


def check_customer_match(mandate: Mandate, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    if proposal.customer_id != mandate.customer_id:
        return CheckResult(
            "customer_match", False, "BLOCK", ReasonCode.INVALID_MANDATE,
            f"Proposal customer {proposal.customer_id!r} does not match "
            f"mandate customer {mandate.customer_id!r}.",
        )
    return CheckResult("customer_match", True, "PASS", None, f"customer={mandate.customer_id}")


def check_currency_match(mandate: Mandate, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    if proposal.currency.upper() != mandate.currency.upper():
        return CheckResult(
            "currency_match", False, "BLOCK", ReasonCode.INVALID_MANDATE,
            f"Proposal currency {proposal.currency} does not match "
            f"mandate currency {mandate.currency}.",
        )
    return CheckResult("currency_match", True, "PASS", None, f"currency={mandate.currency}")


def check_category_allowed(mandate: Mandate, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    allowed = set(mandate.allowed_categories or [])
    if proposal.category not in allowed:
        return CheckResult(
            "category_allowed", False, "BLOCK", ReasonCode.OUT_OF_SCOPE_CATEGORY,
            f"Category {proposal.category!r} is not in the mandate's allowed "
            f"categories {sorted(allowed)}.",
        )
    return CheckResult(
        "category_allowed", True, "PASS", None, f"category {proposal.category!r} allowed",
    )


def check_amount_within_cap(mandate: Mandate, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    remaining = Decimal(mandate.max_amount) - Decimal(mandate.current_period_spend or 0)
    if Decimal(proposal.amount) > remaining:
        return CheckResult(
            "amount_within_cap", False, "BLOCK", ReasonCode.CAP_EXCEEDED,
            f"Requested amount {_fmt_money(proposal.amount, mandate.currency)} "
            f"exceeds the remaining mandate limit of "
            f"{_fmt_money(remaining, mandate.currency)}.",
        )
    return CheckResult(
        "amount_within_cap", True, "PASS", None,
        f"{_fmt_money(proposal.amount, mandate.currency)} within remaining "
        f"{_fmt_money(remaining, mandate.currency)}",
    )


def check_transaction_frequency(mandate: Mandate, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    used = int(mandate.current_period_transactions or 0)
    limit = int(mandate.transaction_limit)
    if used >= limit:
        return CheckResult(
            "transaction_frequency", False, "BLOCK", ReasonCode.WINDOW_EXHAUSTED,
            f"Mandate has used all {limit} allowed transactions for this period.",
        )
    return CheckResult(
        "transaction_frequency", True, "PASS", None, f"tx {used + 1}/{limit}",
    )


def check_price_drift(mandate: Mandate, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    quoted = Decimal(proposal.quoted_price)
    current = Decimal(proposal.current_price)
    if quoted == 0:
        return CheckResult(
            "price_drift", False, "BLOCK", ReasonCode.PRICE_DRIFT,
            "Quoted price is zero — cannot verify current price.",
        )
    drift = abs(current - quoted) / quoted
    tol = Decimal(cfg.price_drift_tolerance)
    if drift > tol:
        return CheckResult(
            "price_drift", False, "BLOCK", ReasonCode.PRICE_DRIFT,
            f"Current price {_fmt_money(current, mandate.currency)} drifted "
            f"{drift * 100:.2f}% from quoted "
            f"{_fmt_money(quoted, mandate.currency)} "
            f"(tolerance {tol * 100:.2f}%).",
        )
    return CheckResult(
        "price_drift", True, "PASS", None,
        f"drift {drift * 100:.2f}% within tolerance",
    )


def check_step_up_rule(mandate: Mandate, proposal: Proposal, now: datetime, cfg: WardenConfig) -> CheckResult:
    threshold = mandate.step_up_over_amount
    if threshold is None:
        return CheckResult("step_up_rule", True, "PASS", None, "no step-up rule configured")
    if Decimal(proposal.amount) > Decimal(threshold):
        return CheckResult(
            "step_up_rule", False, "STEP_UP", ReasonCode.APPROVAL_REQUIRED,
            f"Amount {_fmt_money(proposal.amount, mandate.currency)} exceeds the "
            f"auto-approve threshold of {_fmt_money(threshold, mandate.currency)} "
            "for this mandate. Requires human approval.",
        )
    return CheckResult(
        "step_up_rule", True, "PASS", None,
        f"amount within auto-approve threshold "
        f"{_fmt_money(threshold, mandate.currency)}",
    )


# Ordered as spec's 12-step list, minus step 11 (idempotency) which the
# coordinator handles ahead of the engine. Step-up rule is always last so it
# can only convert an otherwise-ALLOWed decision.
POLICY_ORDER: list[Callable[[Mandate, Proposal, datetime, WardenConfig], CheckResult]] = [
    check_mandate_status,          # 2 (mandate_exists is checked at coordinator load)
    check_within_validity,         # 3
    check_merchant_match,          # 4
    check_customer_match,          # 5
    check_currency_match,          # 6
    check_category_allowed,        # 7
    check_amount_within_cap,       # 8
    check_transaction_frequency,   # 9
    check_price_drift,             # 10
    check_step_up_rule,            # 12
]
