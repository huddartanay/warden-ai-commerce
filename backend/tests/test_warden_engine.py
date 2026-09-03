"""
Pure Warden engine tests.

These tests build Mandate objects in memory (no DB) and call `evaluate`
directly, so they exercise the deterministic policy chain in isolation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.enums import DecisionResult, MandateStatus, ReasonCode
from app.models.mandate import Mandate
from app.warden import Proposal, WardenConfig, evaluate


NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


def _mandate(
    *,
    id: str = "man_x",
    customer_id: str = "cust_x",
    merchant_id: str = "mer_x",
    max_amount: Decimal = Decimal("2000.00"),
    currency: str = "INR",
    categories: list[str] = ["coffee"],
    tx_limit: int = 2,
    validity_start: datetime = NOW - timedelta(days=1),
    validity_end: datetime = NOW + timedelta(days=30),
    status: MandateStatus = MandateStatus.ACTIVE,
    spend: Decimal = Decimal("0"),
    used_tx: int = 0,
    step_up_over: Decimal | None = None,
) -> Mandate:
    return Mandate(
        id=id,
        customer_id=customer_id,
        merchant_id=merchant_id,
        max_amount=max_amount,
        currency=currency,
        allowed_categories=categories,
        transaction_limit=tx_limit,
        validity_start=validity_start,
        validity_end=validity_end,
        status=status,
        current_period_spend=spend,
        current_period_transactions=used_tx,
        step_up_over_amount=step_up_over,
        created_at=NOW,
        updated_at=NOW,
    )


def _proposal(
    *,
    mandate_id: str = "man_x",
    customer_id: str = "cust_x",
    merchant_id: str = "mer_x",
    cart_id: str = "cart_x",
    amount: Decimal = Decimal("500.00"),
    currency: str = "INR",
    category: str = "coffee",
    quoted_price: Decimal = Decimal("500.00"),
    current_price: Decimal = Decimal("500.00"),
    idempotency_key: str = "idem_x",
) -> Proposal:
    return Proposal(
        mandate_id=mandate_id,
        customer_id=customer_id,
        merchant_id=merchant_id,
        cart_id=cart_id,
        amount=amount,
        currency=currency,
        category=category,
        quoted_price=quoted_price,
        current_price=current_price,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------- happy path


def test_valid_transaction_is_allowed():
    m = _mandate()
    p = _proposal(amount=Decimal("1000.00"))
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.ALLOW
    assert d.reason_code == ReasonCode.OK
    # Every non-shortcircuited check should have been run.
    assert [c.name for c in d.checks][:1] == ["mandate_exists"]
    assert all(c.ok for c in d.checks)


# ---------------------------------------------------------------- BLOCK paths


def test_missing_mandate_blocks_with_invalid_mandate():
    d = evaluate(None, _proposal(), now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.INVALID_MANDATE


def test_amount_above_cap_blocks_with_cap_exceeded():
    m = _mandate(max_amount=Decimal("2000.00"))
    p = _proposal(amount=Decimal("3499.00"))
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.CAP_EXCEEDED
    assert "₹3,499.00" in d.explanation and "₹2,000.00" in d.explanation


def test_amount_above_remaining_after_partial_spend_blocks():
    m = _mandate(max_amount=Decimal("2000.00"), spend=Decimal("1500.00"))
    p = _proposal(amount=Decimal("600.00"))
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.CAP_EXCEEDED


def test_category_outside_mandate_blocks():
    m = _mandate(categories=["coffee"])
    p = _proposal(category="appliance", amount=Decimal("500.00"))
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.OUT_OF_SCOPE_CATEGORY


def test_expired_mandate_blocks_by_status():
    m = _mandate(status=MandateStatus.EXPIRED)
    d = evaluate(m, _proposal(), now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.MANDATE_EXPIRED


def test_expired_by_validity_end_blocks_even_if_status_stale():
    # Status still ACTIVE but validity elapsed -> within_validity catches it.
    m = _mandate(
        status=MandateStatus.ACTIVE,
        validity_end=NOW - timedelta(days=1),
    )
    d = evaluate(m, _proposal(), now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.MANDATE_EXPIRED


def test_revoked_mandate_blocks():
    m = _mandate(status=MandateStatus.REVOKED)
    d = evaluate(m, _proposal(), now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.MANDATE_REVOKED


def test_transaction_frequency_exceeded_blocks():
    m = _mandate(tx_limit=1, used_tx=1, status=MandateStatus.PARTIALLY_USED)
    d = evaluate(m, _proposal(amount=Decimal("100.00")), now=NOW)
    assert d.result == DecisionResult.BLOCK
    # Either WINDOW_EXHAUSTED from the status check or the frequency check —
    # both are correct. Assert the one this ordering actually surfaces.
    assert d.reason_code == ReasonCode.WINDOW_EXHAUSTED


def test_price_drift_blocks_with_price_drift():
    m = _mandate()
    # 5% drift, tolerance default 1%
    p = _proposal(
        amount=Decimal("500.00"),
        quoted_price=Decimal("500.00"),
        current_price=Decimal("525.00"),
    )
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.PRICE_DRIFT


def test_price_drift_within_tolerance_is_allowed():
    m = _mandate()
    # 0.5% drift under default 1% tolerance
    p = _proposal(
        amount=Decimal("500.00"),
        quoted_price=Decimal("500.00"),
        current_price=Decimal("502.50"),
    )
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.ALLOW


def test_invalid_merchant_blocks():
    m = _mandate(merchant_id="mer_a")
    p = _proposal(merchant_id="mer_b")
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.INVALID_MANDATE
    assert "merchant" in d.explanation.lower()


def test_invalid_customer_blocks():
    m = _mandate(customer_id="cust_a")
    p = _proposal(customer_id="cust_b")
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.INVALID_MANDATE
    assert "customer" in d.explanation.lower()


def test_currency_mismatch_blocks():
    m = _mandate(currency="INR")
    p = _proposal(currency="USD")
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.INVALID_MANDATE


# ---------------------------------------------------------------- STEP_UP


def test_step_up_when_over_configured_threshold_but_within_cap():
    m = _mandate(max_amount=Decimal("5000.00"), step_up_over=Decimal("2000.00"))
    p = _proposal(amount=Decimal("2500.00"))
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.STEP_UP
    assert d.reason_code == ReasonCode.APPROVAL_REQUIRED


def test_step_up_does_not_fire_when_amount_at_or_below_threshold():
    m = _mandate(max_amount=Decimal("5000.00"), step_up_over=Decimal("2000.00"))
    p = _proposal(amount=Decimal("2000.00"))
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.ALLOW


def test_hard_block_wins_over_step_up():
    # Amount above the step-up threshold AND above the cap -> BLOCK wins.
    m = _mandate(max_amount=Decimal("2000.00"), step_up_over=Decimal("1000.00"))
    p = _proposal(amount=Decimal("2500.00"))
    d = evaluate(m, p, now=NOW)
    assert d.result == DecisionResult.BLOCK
    assert d.reason_code == ReasonCode.CAP_EXCEEDED


# ---------------------------------------------------------------- ordering


def test_short_circuit_on_first_block():
    # Both category and amount are wrong; category is checked earlier so it wins.
    m = _mandate(max_amount=Decimal("100.00"), categories=["coffee"])
    p = _proposal(category="appliance", amount=Decimal("999.00"))
    d = evaluate(m, p, now=NOW)
    assert d.reason_code == ReasonCode.OUT_OF_SCOPE_CATEGORY
    # Later checks were not run.
    names = [c.name for c in d.checks]
    assert "amount_within_cap" not in names
