"""Verify seed_data inserts the expected rows and is idempotent."""

from decimal import Decimal

from sqlalchemy import func, select

from app.models import CatalogItem, Mandate, MandateStatus, Merchant
from app.seed import MERCHANT_ID, seed_data


def test_seed_inserts_expected_rows(session):
    result = seed_data(session)
    session.commit()

    assert result == {"merchants": 1, "catalog_items": 4, "mandates": 3}

    merchant = session.get(Merchant, MERCHANT_ID)
    assert merchant is not None
    assert merchant.name == "Priya's D2C Coffee"

    products = session.execute(select(CatalogItem).order_by(CatalogItem.name)).scalars().all()
    names = [p.name for p in products]
    assert names == [
        "Classic Coffee",
        "Coffee Machine",
        "Espresso Beans",
        "Premium Coffee",
    ]

    mandates = session.execute(select(Mandate).order_by(Mandate.id)).scalars().all()
    caps = {m.id: m.max_amount for m in mandates}
    assert caps == {
        "man_A_regular_2k": Decimal("2000.00"),
        "man_B_bulk_5k": Decimal("5000.00"),
        "man_C_light_1k": Decimal("1000.00"),
    }

    for m in mandates:
        assert m.merchant_id == MERCHANT_ID
        assert m.currency == "INR"
        assert m.allowed_categories == ["coffee"]
        assert m.status == MandateStatus.ACTIVE
        assert m.current_period_spend == Decimal("0")
        assert m.current_period_transactions == 0
        assert m.validity_end > m.validity_start


def test_seed_is_idempotent(session):
    first = seed_data(session)
    session.commit()
    second = seed_data(session)
    session.commit()

    assert first == {"merchants": 1, "catalog_items": 4, "mandates": 3}
    assert second == {"merchants": 0, "catalog_items": 0, "mandates": 0}

    assert session.scalar(select(func.count()).select_from(Merchant)) == 1
    assert session.scalar(select(func.count()).select_from(CatalogItem)) == 4
    assert session.scalar(select(func.count()).select_from(Mandate)) == 3
