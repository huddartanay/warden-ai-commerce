"""Agent tools — pure Python readers over the seeded catalog + mandates."""

from __future__ import annotations

from decimal import Decimal

from app.agents.tools import (
    check_mandate,
    find_active_mandate_for_customer,
    get_product,
    quote_cart,
    search_catalog,
)
from app.seed import seed_data


def _seeded(session):
    seed_data(session)
    session.commit()


def test_search_catalog_finds_coffee_products(session):
    _seeded(session)
    results = search_catalog(session, merchant_id="mer_priya_coffee", category="coffee")
    names = [p.name for p in results]
    # Two coffee items exist in seed: Classic Coffee, Premium Coffee.
    assert set(names) == {"Classic Coffee", "Premium Coffee"}
    # Sorted cheapest-first.
    assert [p.price for p in results] == sorted(p.price for p in results)


def test_search_catalog_respects_max_price(session):
    _seeded(session)
    results = search_catalog(
        session, merchant_id="mer_priya_coffee", max_price=Decimal("500.00")
    )
    for p in results:
        assert p.price <= Decimal("500.00")


def test_search_catalog_query_partial_name(session):
    _seeded(session)
    results = search_catalog(
        session, merchant_id="mer_priya_coffee", query="espresso"
    )
    assert any(p.name == "Espresso Beans" for p in results)


def test_get_product_returns_view(session):
    _seeded(session)
    p = get_product(session, "cat_classic_coffee")
    assert p is not None
    assert p.name == "Classic Coffee"
    assert p.price == Decimal("699.00")


def test_get_product_missing(session):
    _seeded(session)
    assert get_product(session, "cat_does_not_exist") is None


def test_quote_cart_sums_and_ignores_unknown(session):
    _seeded(session)
    quote = quote_cart(
        session,
        selections=[
            {"catalog_item_id": "cat_classic_coffee", "quantity": 2},
            {"catalog_item_id": "cat_premium_coffee", "quantity": 1},
            {"catalog_item_id": "cat_missing", "quantity": 1},  # dropped
        ],
    )
    # 2 * 699 + 800 = 2198
    assert quote.total == Decimal("2198.00")
    assert len(quote.items) == 2
    assert quote.currency == "INR"


def test_check_mandate_returns_view_with_remaining(session):
    _seeded(session)
    view = check_mandate(session, "man_A_regular_2k")
    assert view is not None
    assert view.remaining_amount == Decimal("2000.00")
    assert view.remaining_transactions == 1
    assert view.allowed_categories == ["coffee"]


def test_check_mandate_missing(session):
    _seeded(session)
    assert check_mandate(session, "man_ghost") is None


def test_find_active_mandate_for_customer_picks_the_active_one(session):
    _seeded(session)
    view = find_active_mandate_for_customer(session, customer_id="cust_priya_regular")
    assert view is not None
    assert view.id == "man_A_regular_2k"
