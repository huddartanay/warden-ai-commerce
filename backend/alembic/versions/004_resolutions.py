"""Create resolutions table.

Revision ID: 004_resolutions
Revises: 003_action_status_refunded
Create Date: 2026-09-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_resolutions"
down_revision: Union[str, None] = "003_action_status_refunded"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RESOLUTION_STATUS = ("PENDING_UNRESOLVED", "REQUIRES_HUMAN", "RESOLVED")


def upgrade() -> None:
    op.create_table(
        "resolutions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "action_id",
            sa.String(length=64),
            sa.ForeignKey("actions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                *RESOLUTION_STATUS,
                name="resolution_status",
                native_enum=False,
                length=32,
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("resolved_by", sa.String(length=64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("resolutions")
