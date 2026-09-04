"""Add mandates.rolling_window_seconds + CUMULATIVE_SPEND_EXCEEDED reason.

Revision ID: 007_rolling_window
Revises: 006_agent_credentials
Create Date: 2026-09-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_rolling_window"
down_revision: Union[str, None] = "006_agent_credentials"
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
    "AGENT_AUTH_FAILED",
)
NEW_REASON_CODES = OLD_REASON_CODES + ("CUMULATIVE_SPEND_EXCEEDED",)


def upgrade() -> None:
    with op.batch_alter_table("mandates") as batch:
        batch.add_column(
            sa.Column("rolling_window_seconds", sa.Integer(), nullable=True)
        )
        batch.add_column(
            sa.Column("rolling_window_max_amount", sa.Numeric(14, 2), nullable=True)
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
    with op.batch_alter_table("mandates") as batch:
        batch.drop_column("rolling_window_max_amount")
        batch.drop_column("rolling_window_seconds")
