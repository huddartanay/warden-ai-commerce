"""Create agent_credentials table + allow AGENT_AUTH_FAILED reason.

Revision ID: 006_agent_credentials
Revises: 005_mandate_version
Create Date: 2026-09-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_agent_credentials"
down_revision: Union[str, None] = "005_mandate_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_REASON_CODES = (
    "OK",
    "CAP_EXCEEDED",
    "WINDOW_EXHAUSTED",
    "OUT_OF_SCOPE_CATEGORY",
    "PRICE_DRIFT",
    "DUPLICATE_ACTION",
    "MANDATE_EXPIRED",
    "MANDATE_REVOKED",
    "INVALID_MANDATE",
    "SYSTEM_ERROR",
    "APPROVAL_REQUIRED",
    "CONCURRENT_UPDATE",
)
NEW_REASON_CODES = OLD_REASON_CODES + ("AGENT_AUTH_FAILED",)


def upgrade() -> None:
    op.create_table(
        "agent_credentials",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "mandate_id",
            sa.String(length=64),
            sa.ForeignKey("mandates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("secret", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    with op.batch_alter_table("decisions") as batch:
        batch.alter_column(
            "reason_code",
            existing_type=sa.Enum(
                *OLD_REASON_CODES, name="reason_code", native_enum=False, length=32
            ),
            type_=sa.Enum(
                *NEW_REASON_CODES, name="reason_code", native_enum=False, length=32
            ),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("decisions") as batch:
        batch.alter_column(
            "reason_code",
            existing_type=sa.Enum(
                *NEW_REASON_CODES, name="reason_code", native_enum=False, length=32
            ),
            type_=sa.Enum(
                *OLD_REASON_CODES, name="reason_code", native_enum=False, length=32
            ),
            existing_nullable=False,
        )
    op.drop_table("agent_credentials")
