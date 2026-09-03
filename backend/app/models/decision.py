from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import DecisionResult, ReasonCode


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Decision(Base):
    """
    The deterministic verdict produced by Warden Core for an Action.
    One Action -> one Decision.
    """

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("actions.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    result: Mapped[DecisionResult] = mapped_column(
        Enum(
            DecisionResult,
            name="decision_result",
            native_enum=False,
            length=16,
            validate_strings=True,
        ),
        nullable=False,
    )
    reason_code: Mapped[ReasonCode] = mapped_column(
        Enum(
            ReasonCode,
            name="reason_code",
            native_enum=False,
            length=32,
            validate_strings=True,
        ),
        nullable=False,
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<Decision {self.id} action={self.action_id} "
            f"{self.result.value} ({self.reason_code.value})>"
        )
