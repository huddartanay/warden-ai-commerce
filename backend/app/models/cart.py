from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Cart(Base):
    """
    A proposed set of catalog items assembled by an AI buyer for a mandate.
    Cart itself is inert — it becomes financially meaningful only when an
    Action wraps it and Warden evaluates that action.
    """

    __tablename__ = "carts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mandate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("mandates.id", ondelete="CASCADE"), nullable=False
    )
    merchant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )

    # List of {catalog_item_id, name, category, unit_price, quantity, line_total}
    items: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)

    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    # Period key (e.g. "2026-09") used inside the idempotency hash.
    period: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    def __repr__(self) -> str:
        return f"<Cart {self.id} total={self.currency}{self.total_amount}>"
