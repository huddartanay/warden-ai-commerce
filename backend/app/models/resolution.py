from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import ResolutionStatus


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Resolution(Base):
    """
    Human-facing queue entry for an Action that needs attention.

    One row per action_id (upserted). Records the current queue status, a
    human-readable note, and — once handled — who and when.
    """

    __tablename__ = "resolutions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("actions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    status: Mapped[ResolutionStatus] = mapped_column(
        Enum(
            ResolutionStatus,
            name="resolution_status",
            native_enum=False,
            length=32,
            validate_strings=True,
        ),
        nullable=False,
        index=True,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<Resolution action={self.action_id} status={self.status.value}>"
