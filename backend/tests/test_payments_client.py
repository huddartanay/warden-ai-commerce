"""RazorpayClient — mock behavior + safety guards on live init."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.payments import (
    LiveRazorpayClient,
    MockRazorpayClient,
    RazorpayError,
    RazorpayRetryable,
    paise_to_rupees,
    retry_read,
    rupees_to_paise,
)


# ---- money -----------------------------------------------------------------


def test_rupees_to_paise_basic():
    assert rupees_to_paise(Decimal("1499.00")) == 149900
    assert rupees_to_paise(Decimal("0.01")) == 1
    assert rupees_to_paise(Decimal("0")) == 0


def test_rupees_to_paise_rounds_half_up():
    assert rupees_to_paise(Decimal("10.005")) == 1001  # 10.005 -> 10.01 -> 1001p
    assert rupees_to_paise(Decimal("10.004")) == 1000


def test_paise_to_rupees_roundtrip():
    assert paise_to_rupees(149900) == Decimal("1499.00")


# ---- MockRazorpayClient ----------------------------------------------------


def test_mock_create_order_is_deterministic():
    c = MockRazorpayClient()
    a = c.create_order(amount_paise=149900, currency="INR", receipt="idem_1")
    b = c.create_order(amount_paise=149900, currency="INR", receipt="idem_1")
    assert a["id"] == b["id"], "same receipt should yield same mock order id"
    assert a["id"].startswith("order_MOCK")
    assert a["amount"] == 149900
    assert a["currency"] == "INR"
    assert a["status"] == "created"


def test_mock_create_payment_link_shape():
    c = MockRazorpayClient()
    r = c.create_payment_link(
        amount_paise=100, currency="INR", reference_id="act_x", description="test"
    )
    assert r["id"].startswith("plink_MOCK")
    assert r["short_url"].startswith("https://rzp.io/i/mock/")
    assert r["status"] == "created"


def test_mock_capture_and_refund():
    c = MockRazorpayClient()
    cap = c.capture_payment("pay_MOCK123", amount_paise=100)
    assert cap["status"] == "captured"

    ref = c.refund_payment("pay_MOCK123", amount_paise=100)
    assert ref["id"].startswith("rfnd_MOCK")
    assert ref["status"] == "processed"


# ---- LiveRazorpayClient safety --------------------------------------------


def test_live_client_refuses_production_keys():
    with pytest.raises(RazorpayError) as ei:
        LiveRazorpayClient(key_id="rzp_live_ABC", key_secret="s")
    assert "TEST MODE ONLY" in str(ei.value)


def test_live_client_requires_both_key_and_secret():
    with pytest.raises(RazorpayError):
        LiveRazorpayClient(key_id="", key_secret="s")
    with pytest.raises(RazorpayError):
        LiveRazorpayClient(key_id="rzp_test_ABC", key_secret="")


# ---- retry_read ------------------------------------------------------------


def test_retry_read_returns_on_success():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return {"ok": True}

    assert retry_read(fn, tries=3, base_delay_s=0) == {"ok": True}
    assert calls["n"] == 1


def test_retry_read_retries_only_retryable():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RazorpayRetryable("temp")
        return {"ok": True}

    assert retry_read(fn, tries=3, base_delay_s=0) == {"ok": True}
    assert calls["n"] == 2


def test_retry_read_does_not_retry_non_retryable():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise RazorpayError("hard")

    with pytest.raises(RazorpayError):
        retry_read(fn, tries=3, base_delay_s=0)
    assert calls["n"] == 1


def test_retry_read_gives_up_after_max_tries():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise RazorpayRetryable("still bad")

    with pytest.raises(RazorpayRetryable):
        retry_read(fn, tries=3, base_delay_s=0)
    assert calls["n"] == 3
