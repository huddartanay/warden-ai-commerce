from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class RazorpayRef(Base):
    """
    Every Razorpay resource we create/observe (order, payment_link, payment,
    refund) is recorded here and tied back to the authorizing Action.
    """

    __tablename__ = "razorpay_refs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("actions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # e.g. "order" | "payment_link" | "payment" | "refund"
    ref_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # The Razorpay-side id (order_xxx, plink_xxx, pay_xxx, rfnd_xxx).
    razorpay_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<RazorpayRef {self.ref_type} {self.razorpay_id} action={self.action_id}>"
