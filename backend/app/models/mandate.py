from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import MandateStatus


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Mandate(Base):
    """
    A customer's bounded authorization for an AI buyer to spend on their behalf,
    at one merchant, within a set of rules. Warden treats the mandate as the
    ground truth for what is allowed.
    """

    __tablename__ = "mandates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    customer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )

    max_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    # List of allowed catalog categories (e.g. ["coffee", "beans"]).
    allowed_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Max number of transactions permitted per period.
    transaction_limit: Mapped[int] = mapped_column(Integer, nullable=False)

    validity_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    validity_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    status: Mapped[MandateStatus] = mapped_column(
        Enum(
            MandateStatus,
            name="mandate_status",
            native_enum=False,
            length=32,
            validate_strings=True,
        ),
        nullable=False,
        default=MandateStatus.ACTIVE,
    )

    current_period_spend: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    current_period_transactions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Soft threshold — a single proposal above this amount (but still within
    # max_amount) is routed to STEP_UP APPROVAL_REQUIRED instead of ALLOW.
    # NULL disables the rule.
    step_up_over_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="mandates")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<Mandate {self.id} customer={self.customer_id} "
            f"max={self.currency}{self.max_amount} status={self.status.value}>"
        )
