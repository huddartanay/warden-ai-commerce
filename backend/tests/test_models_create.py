"""Verify every table is created and accepts a minimal row."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import inspect, select

from app.models import (
    Action,
    ActionStatus,
    ActionType,
    AuditLog,
    Cart,
    CatalogItem,
    Decision,
    DecisionResult,
    Mandate,
    MandateStatus,
    Merchant,
    RazorpayRef,
    ReasonCode,
)


EXPECTED_TABLES = {
    "merchants",
    "catalog_items",
    "mandates",
    "carts",
    "actions",
    "decisions",
    "audit_log",
    "razorpay_refs",
}


def test_all_expected_tables_exist(engine):
    tables = set(inspect(engine).get_table_names())
    missing = EXPECTED_TABLES - tables
    assert not missing, f"missing tables: {missing}"


def test_end_to_end_insert(session):
    now = datetime.now(tz=timezone.utc)

    merchant = Merchant(id="mer_t", name="Test Co", created_at=now, updated_at=now)
    session.add(merchant)

    item = CatalogItem(
        id="cat_t",
        merchant_id="mer_t",
        name="Widget",
        category="misc",
        price=Decimal("100.00"),
        currency="INR",
        available=True,
        created_at=now,
        updated_at=now,
    )
    session.add(item)

    mandate = Mandate(
        id="man_t",
        customer_id="cust_t",
        merchant_id="mer_t",
        max_amount=Decimal("500.00"),
        currency="INR",
        allowed_categories=["misc"],
        transaction_limit=3,
        validity_start=now,
        validity_end=now + timedelta(days=30),
        status=MandateStatus.ACTIVE,
        current_period_spend=Decimal("0"),
        current_period_transactions=0,
        created_at=now,
        updated_at=now,
    )
    session.add(mandate)

    cart = Cart(
        id="cart_t",
        mandate_id="man_t",
        merchant_id="mer_t",
        items=[
            {
                "catalog_item_id": "cat_t",
                "name": "Widget",
                "category": "misc",
                "unit_price": "100.00",
                "quantity": 2,
                "line_total": "200.00",
            }
        ],
        total_amount=Decimal("200.00"),
        currency="INR",
        period="2026-09",
        created_at=now,
    )
    session.add(cart)

    action = Action(
        id="act_t",
        mandate_id="man_t",
        cart_id="cart_t",
        action_type=ActionType.PAYMENT,
        amount=Decimal("200.00"),
        currency="INR",
        idempotency_key="idem_test_1",
        status=ActionStatus.PROPOSED,
        created_at=now,
        updated_at=now,
    )
    session.add(action)

    decision = Decision(
        id="dec_t",
        action_id="act_t",
        result=DecisionResult.ALLOW,
        reason_code=ReasonCode.OK,
        explanation="all checks passed",
        created_at=now,
    )
    session.add(decision)

    session.add(
        AuditLog(
            event_id="evt_t",
            action_id="act_t",
            event_type="TEST",
            event_data={"hello": "world"},
            previous_hash="0" * 64,
            current_hash="a" * 64,
            timestamp=now,
        )
    )

    session.add(
        RazorpayRef(
            id="rzp_t",
            action_id="act_t",
            ref_type="order",
            razorpay_id="order_test_1",
            status="created",
            raw_response={"ok": True},
            created_at=now,
            updated_at=now,
        )
    )

    session.commit()

    assert session.get(Merchant, "mer_t") is not None
    assert session.get(Decision, "dec_t").result == DecisionResult.ALLOW
    assert session.execute(select(AuditLog)).scalars().first().event_type == "TEST"
