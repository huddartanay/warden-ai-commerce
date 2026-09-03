from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import ActionStatus, ActionType


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Action(Base):
    """
    A proposed financial action against a mandate. Every Action carries a
    deterministic idempotency_key derived from (mandate_id, cart_id, period)
    so the same logical proposal can never result in two financial actions.
    """

    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mandate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("mandates.id", ondelete="CASCADE"), nullable=False
    )
    cart_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("carts.id", ondelete="SET NULL"), nullable=True
    )

    action_type: Mapped[ActionType] = mapped_column(
        Enum(
            ActionType,
            name="action_type",
            native_enum=False,
            length=32,
            validate_strings=True,
        ),
        nullable=False,
        default=ActionType.PAYMENT,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    # sha256(mandate_id || cart_id || period). Unique — enforces no-double-charge.
    idempotency_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )

    status: Mapped[ActionStatus] = mapped_column(
        Enum(
            ActionStatus,
            name="action_status",
            native_enum=False,
            length=32,
            validate_strings=True,
        ),
        nullable=False,
        default=ActionStatus.PROPOSED,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<Action {self.id} {self.action_type.value} "
            f"{self.currency}{self.amount} status={self.status.value}>"
        )
