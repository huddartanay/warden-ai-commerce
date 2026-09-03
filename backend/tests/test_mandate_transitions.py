"""Exercise the mandate state machine."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Mandate, MandateStatus, Merchant
from app.services.mandate_state import (
    apply_successful_action,
    recompute_status,
    refresh_status,
    revoke,
)


@pytest.fixture
def merchant(session):
    now = datetime.now(tz=timezone.utc)
    m = Merchant(id="mer_state", name="M", created_at=now, updated_at=now)
    session.add(m)
    session.flush()
    return m


def _make_mandate(
    session,
    merchant,
    *,
    max_amount=Decimal("2000.00"),
    tx_limit=1,
    validity_days=30,
    status=MandateStatus.ACTIVE,
    spend=Decimal("0"),
    used_tx=0,
) -> Mandate:
    now = datetime.now(tz=timezone.utc)
    m = Mandate(
        id=f"man_state_{used_tx}_{spend}",
        customer_id="cust_x",
        merchant_id=merchant.id,
        max_amount=max_amount,
        currency="INR",
        allowed_categories=["coffee"],
        transaction_limit=tx_limit,
        validity_start=now - timedelta(days=1),
        validity_end=now + timedelta(days=validity_days),
        status=status,
        current_period_spend=spend,
        current_period_transactions=used_tx,
        created_at=now,
        updated_at=now,
    )
    session.add(m)
    session.flush()
    return m


def test_fresh_mandate_is_active(session, merchant):
    m = _make_mandate(session, merchant)
    assert recompute_status(m) == MandateStatus.ACTIVE


def test_partial_spend_becomes_partially_used(session, merchant):
    m = _make_mandate(session, merchant, max_amount=Decimal("2000.00"), tx_limit=3, spend=Decimal("500.00"), used_tx=1)
    assert recompute_status(m) == MandateStatus.PARTIALLY_USED


def test_spend_at_or_over_cap_is_exhausted(session, merchant):
    m = _make_mandate(session, merchant, max_amount=Decimal("2000.00"), tx_limit=5, spend=Decimal("2000.00"))
    assert recompute_status(m) == MandateStatus.EXHAUSTED

    m2 = _make_mandate(session, merchant, max_amount=Decimal("2000.00"), tx_limit=5, spend=Decimal("2100.00"))
    assert recompute_status(m2) == MandateStatus.EXHAUSTED


def test_transaction_limit_reached_is_exhausted(session, merchant):
    m = _make_mandate(session, merchant, tx_limit=1, spend=Decimal("100.00"), used_tx=1)
    assert recompute_status(m) == MandateStatus.EXHAUSTED


def test_expired_when_past_validity_end(session, merchant):
    m = _make_mandate(session, merchant)
    long_ago = datetime.now(tz=timezone.utc) + timedelta(days=365)
    assert recompute_status(m, now=long_ago) == MandateStatus.EXPIRED


def test_revoked_is_sticky(session, merchant):
    m = _make_mandate(session, merchant, status=MandateStatus.REVOKED)
    # Even with fresh state, revoked stays revoked.
    assert recompute_status(m) == MandateStatus.REVOKED


def test_revoke_helper_marks_revoked(session, merchant):
    m = _make_mandate(session, merchant)
    revoke(m)
    assert m.status == MandateStatus.REVOKED
    # ...and recompute agrees.
    assert recompute_status(m) == MandateStatus.REVOKED


def test_refresh_status_mutates_row(session, merchant):
    m = _make_mandate(session, merchant, tx_limit=1, spend=Decimal("100.00"), used_tx=1)
    new = refresh_status(m)
    assert new == MandateStatus.EXHAUSTED
    assert m.status == MandateStatus.EXHAUSTED


def test_apply_successful_action_updates_counters_and_status(session, merchant):
    m = _make_mandate(session, merchant, max_amount=Decimal("2000.00"), tx_limit=3)
    new = apply_successful_action(m, amount=Decimal("700.00"))
    assert new == MandateStatus.PARTIALLY_USED
    assert m.current_period_spend == Decimal("700.00")
    assert m.current_period_transactions == 1

    apply_successful_action(m, amount=Decimal("1300.00"))
    # Reached cap exactly -> EXHAUSTED
    assert m.status == MandateStatus.EXHAUSTED
    assert m.current_period_spend == Decimal("2000.00")
    assert m.current_period_transactions == 2
