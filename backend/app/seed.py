"""
Seed the demo data: Priya's D2C Coffee, four catalog items, three mandates.

Idempotent — running twice will not duplicate rows. Uses fixed IDs so tests can
assert on them and the demo UI has predictable references.

Usage:
    python -m app.seed                # seeds the DB pointed at by DATABASE_URL
    python -m app.seed --url sqlite:///demo.db
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import Base
from app.models import CatalogItem, Mandate, MandateStatus, Merchant

# ---- Fixed IDs --------------------------------------------------------------

MERCHANT_ID = "mer_priya_coffee"

CATALOG_ITEMS: list[dict] = [
    {"id": "cat_classic_coffee", "name": "Classic Coffee", "category": "coffee", "price": Decimal("699.00")},
    {"id": "cat_premium_coffee", "name": "Premium Coffee", "category": "coffee", "price": Decimal("800.00")},
    {"id": "cat_espresso_beans", "name": "Espresso Beans", "category": "beans",  "price": Decimal("450.00")},
    {"id": "cat_coffee_machine", "name": "Coffee Machine", "category": "appliance", "price": Decimal("3499.00")},
]

MANDATES: list[dict] = [
    {
        "id": "man_A_regular_2k",
        "customer_id": "cust_priya_regular",
        "max_amount": Decimal("2000.00"),
        "allowed_categories": ["coffee"],
        "transaction_limit": 1,
        "validity_days": 90,
    },
    {
        "id": "man_B_bulk_5k",
        "customer_id": "cust_bulk_buyer",
        "max_amount": Decimal("5000.00"),
        "allowed_categories": ["coffee"],
        "transaction_limit": 2,
        "validity_days": 90,
    },
    {
        "id": "man_C_light_1k",
        "customer_id": "cust_light_user",
        "max_amount": Decimal("1000.00"),
        "allowed_categories": ["coffee"],
        "transaction_limit": 1,
        "validity_days": 90,
    },
]


# ---- Seeder ----------------------------------------------------------------


def seed_data(session: Session, *, now: datetime | None = None) -> dict:
    """Insert seed rows. Safe to call multiple times."""
    when = now or datetime.now(tz=timezone.utc)
    created = {"merchants": 0, "catalog_items": 0, "mandates": 0}

    # Merchant
    merchant = session.get(Merchant, MERCHANT_ID)
    if merchant is None:
        merchant = Merchant(
            id=MERCHANT_ID,
            name="Priya's D2C Coffee",
            display_name="Priya's D2C Coffee",
            created_at=when,
            updated_at=when,
        )
        session.add(merchant)
        created["merchants"] += 1

    # Catalog items
    for item in CATALOG_ITEMS:
        if session.get(CatalogItem, item["id"]) is None:
            session.add(
                CatalogItem(
                    id=item["id"],
                    merchant_id=MERCHANT_ID,
                    name=item["name"],
                    category=item["category"],
                    price=item["price"],
                    currency="INR",
                    available=True,
                    created_at=when,
                    updated_at=when,
                )
            )
            created["catalog_items"] += 1

    # Mandates
    for m in MANDATES:
        if session.get(Mandate, m["id"]) is None:
            session.add(
                Mandate(
                    id=m["id"],
                    customer_id=m["customer_id"],
                    merchant_id=MERCHANT_ID,
                    max_amount=m["max_amount"],
                    currency="INR",
                    allowed_categories=m["allowed_categories"],
                    transaction_limit=m["transaction_limit"],
                    validity_start=when,
                    validity_end=when + timedelta(days=m["validity_days"]),
                    status=MandateStatus.ACTIVE,
                    current_period_spend=Decimal("0"),
                    current_period_transactions=0,
                    created_at=when,
                    updated_at=when,
                )
            )
            created["mandates"] += 1

    session.flush()
    return created


def seed_summary(session: Session) -> dict[str, int]:
    return {
        "merchants": session.scalar(select(Merchant.id).where(Merchant.id == MERCHANT_ID).exists().select()) or 0,  # type: ignore[arg-type]
        "catalog_items": _count(session, CatalogItem),
        "mandates": _count(session, Mandate),
    }


def _count(session: Session, model) -> int:
    from sqlalchemy import func

    return int(session.scalar(select(func.count()).select_from(model)) or 0)


# ---- CLI --------------------------------------------------------------------


def _run_cli(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed Warden's demo data.")
    parser.add_argument(
        "--url",
        default=None,
        help="Override DATABASE_URL for this run (e.g. sqlite:///demo.db).",
    )
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help="Run Base.metadata.create_all() before seeding. Useful for SQLite.",
    )
    args = parser.parse_args(argv)

    url = args.url or get_settings().database_url
    engine = create_engine(url, future=True)

    if args.create_tables:
        Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal.begin() as session:
        result = seed_data(session)

    with SessionLocal() as session:
        totals = {
            "merchants": _count(session, Merchant),
            "catalog_items": _count(session, CatalogItem),
            "mandates": _count(session, Mandate),
        }

    print(f"seeded (this run inserted): {result}")
    print(f"totals in DB now:           {totals}")


if __name__ == "__main__":
    _run_cli()
