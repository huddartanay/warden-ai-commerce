"""
Agent tools.

These are pure Python functions that read the DB and never mutate financial
state. They are the ONLY DB-facing surface the agent uses to gather context
before proposing a cart.

Rule: no tool in this file may cause money to move or approve a payment.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import CatalogItem, Mandate, MandateStatus


# ---- Return types -----------------------------------------------------------


@dataclass(frozen=True)
class ProductView:
    id: str
    merchant_id: str
    name: str
    category: str
    price: Decimal
    currency: str
    available: bool

    @classmethod
    def from_row(cls, row: CatalogItem) -> "ProductView":
        return cls(
            id=row.id,
            merchant_id=row.merchant_id,
            name=row.name,
            category=row.category,
            price=Decimal(row.price),
            currency=row.currency,
            available=row.available,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "merchant_id": self.merchant_id,
            "name": self.name,
            "category": self.category,
            "price": str(self.price),
            "currency": self.currency,
            "available": self.available,
        }


@dataclass(frozen=True)
class CartLine:
    catalog_item_id: str
    name: str
    category: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal

    def to_dict(self) -> dict:
        return {
            "catalog_item_id": self.catalog_item_id,
            "name": self.name,
            "category": self.category,
            "quantity": self.quantity,
            "unit_price": str(self.unit_price),
            "line_total": str(self.line_total),
        }


@dataclass(frozen=True)
class Quote:
    items: list[CartLine]
    total: Decimal
    currency: str

    def to_dict(self) -> dict:
        return {
            "items": [i.to_dict() for i in self.items],
            "total": str(self.total),
            "currency": self.currency,
        }


@dataclass(frozen=True)
class MandateView:
    id: str
    customer_id: str
    merchant_id: str
    max_amount: Decimal
    currency: str
    allowed_categories: list[str]
    transaction_limit: int
    status: MandateStatus
    current_period_spend: Decimal
    current_period_transactions: int
    remaining_amount: Decimal
    remaining_transactions: int
    step_up_over_amount: Decimal | None

    @classmethod
    def from_row(cls, row: Mandate) -> "MandateView":
        max_amount = Decimal(row.max_amount)
        spend = Decimal(row.current_period_spend or 0)
        tx_used = int(row.current_period_transactions or 0)
        return cls(
            id=row.id,
            customer_id=row.customer_id,
            merchant_id=row.merchant_id,
            max_amount=max_amount,
            currency=row.currency,
            allowed_categories=list(row.allowed_categories or []),
            transaction_limit=int(row.transaction_limit),
            status=row.status,
            current_period_spend=spend,
            current_period_transactions=tx_used,
            remaining_amount=max_amount - spend,
            remaining_transactions=max(0, int(row.transaction_limit) - tx_used),
            step_up_over_amount=(
                Decimal(row.step_up_over_amount) if row.step_up_over_amount is not None else None
            ),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "merchant_id": self.merchant_id,
            "max_amount": str(self.max_amount),
            "currency": self.currency,
            "allowed_categories": self.allowed_categories,
            "transaction_limit": self.transaction_limit,
            "status": self.status.value,
            "current_period_spend": str(self.current_period_spend),
            "current_period_transactions": self.current_period_transactions,
            "remaining_amount": str(self.remaining_amount),
            "remaining_transactions": self.remaining_transactions,
            "step_up_over_amount": (
                str(self.step_up_over_amount)
                if self.step_up_over_amount is not None
                else None
            ),
        }


# ---- Tool implementations ---------------------------------------------------


def search_catalog(
    session: Session,
    *,
    merchant_id: str,
    query: str | None = None,
    category: str | None = None,
    max_price: Decimal | None = None,
    available_only: bool = True,
    limit: int = 20,
) -> list[ProductView]:
    """
    Search catalog items for a merchant. Simple LIKE-based name match plus
    optional category and price ceiling. No LLM.
    """
    conditions = [CatalogItem.merchant_id == merchant_id]
    if available_only:
        conditions.append(CatalogItem.available.is_(True))
    if category is not None:
        conditions.append(CatalogItem.category == category)
    if max_price is not None:
        conditions.append(CatalogItem.price <= max_price)
    if query:
        needle = f"%{query.lower()}%"
        conditions.append(
            or_(
                CatalogItem.name.ilike(needle),
                CatalogItem.category.ilike(needle),
            )
        )

    stmt = (
        select(CatalogItem)
        .where(and_(*conditions))
        .order_by(CatalogItem.price.asc(), CatalogItem.name.asc())
        .limit(limit)
    )
    rows = session.execute(stmt).scalars().all()
    return [ProductView.from_row(r) for r in rows]


def get_product(session: Session, catalog_item_id: str) -> ProductView | None:
    row = session.get(CatalogItem, catalog_item_id)
    return ProductView.from_row(row) if row else None


def quote_cart(
    session: Session,
    *,
    selections: list[dict],  # [{catalog_item_id, quantity}, ...]
) -> Quote:
    """
    Look up each selection against the catalog and produce a Quote using CURRENT
    catalog prices. The caller (agent) is responsible for storing the quoted
    price separately if it wants Warden to check price drift.
    """
    lines: list[CartLine] = []
    total = Decimal("0")
    currency = "INR"
    for sel in selections:
        item_id = sel["catalog_item_id"]
        qty = int(sel.get("quantity", 1))
        if qty <= 0:
            continue
        item = session.get(CatalogItem, item_id)
        if item is None or not item.available:
            continue
        unit_price = Decimal(item.price)
        line_total = unit_price * qty
        lines.append(
            CartLine(
                catalog_item_id=item.id,
                name=item.name,
                category=item.category,
                quantity=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )
        total += line_total
        currency = item.currency
    return Quote(items=lines, total=total, currency=currency)


def check_mandate(session: Session, mandate_id: str) -> MandateView | None:
    """Read a mandate — no mutation, no state transition."""
    row = session.get(Mandate, mandate_id)
    return MandateView.from_row(row) if row else None


def find_active_mandate_for_customer(
    session: Session, *, customer_id: str, merchant_id: str | None = None
) -> MandateView | None:
    """Pick the first ACTIVE/PARTIALLY_USED mandate for a customer."""
    conditions = [
        Mandate.customer_id == customer_id,
        Mandate.status.in_([MandateStatus.ACTIVE, MandateStatus.PARTIALLY_USED]),
    ]
    if merchant_id:
        conditions.append(Mandate.merchant_id == merchant_id)
    stmt = (
        select(Mandate).where(and_(*conditions)).order_by(Mandate.created_at.asc()).limit(1)
    )
    row = session.execute(stmt).scalar_one_or_none()
    return MandateView.from_row(row) if row else None
