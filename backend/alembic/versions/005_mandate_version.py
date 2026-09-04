"""Add mandates.version for optimistic-concurrency compare-and-swap.

Also extend the reason_code CHECK constraint on decisions to allow
CONCURRENT_UPDATE.

Revision ID: 005_mandate_version
Revises: 004_resolutions
Create Date: 2026-09-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_mandate_version"
down_revision: Union[str, None] = "004_resolutions"
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
)
NEW_REASON_CODES = OLD_REASON_CODES + ("CONCURRENT_UPDATE",)


def upgrade() -> None:
    with op.batch_alter_table("mandates") as batch:
        batch.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="0")
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
        batch.drop_column("version")
