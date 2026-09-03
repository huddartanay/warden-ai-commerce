from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class AuditLog(Base):
    """
    Append-only, hash-chained audit trail.

    seq is a monotonic sequence used for chain ordering (timestamps can tie).
    current_hash = SHA256(previous_hash || event_type || canonical_json(event_data)).
    """

    __tablename__ = "audit_log"

    # Monotonic sequence used for chain ordering. Also the physical PK.
    # BigInteger on Postgres; plain Integer on SQLite so the rowid-alias
    # autoincrement kicks in (SQLite only autoincrements INTEGER PRIMARY KEY).
    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )

    event_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )

    action_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("actions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    current_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )

    def __repr__(self) -> str:
        return f"<AuditLog seq={self.seq} {self.event_type} action={self.action_id}>"
