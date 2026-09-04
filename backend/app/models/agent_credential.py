from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class AgentCredential(Base):
    """
    A scoped credential issued to one AI Buyer Agent instance, tied to
    exactly one mandate.

    The agent signs every proposal with `HMAC-SHA256(secret, canonical_json)`;
    Warden verifies before any policy check runs. A credential valid for
    mandate A CANNOT authorize a proposal targeting mandate B, even with a
    correctly formed HMAC — the auth layer checks mandate_id match.

    NOTE: For hackathon simplicity the secret is stored in plaintext. In
    production this table would be encrypted at rest or the secret would be
    wrapped by a KMS key.
    """

    __tablename__ = "agent_credentials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # agent_id
    mandate_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("mandates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    secret: Mapped[str] = mapped_column(String(128), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<AgentCredential {self.id} mandate={self.mandate_id}>"
