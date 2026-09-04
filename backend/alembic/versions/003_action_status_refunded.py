"""Add REFUNDED to action_status.

Revision ID: 003_action_status_refunded
Revises: 002_mandate_step_up
Create Date: 2026-09-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_action_status_refunded"
down_revision: Union[str, None] = "002_mandate_step_up"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_ACTION_STATUS = (
    "PROPOSED",
    "ALLOWED",
    "BLOCKED",
    "STEP_UP_PENDING",
    "STEP_UP_APPROVED",
    "STEP_UP_REJECTED",
    "PAYMENT_INITIATED",
    "PAYMENT_COMPLETED",
    "PAYMENT_FAILED",
    "PENDING_UNRESOLVED",
)
NEW_ACTION_STATUS = OLD_ACTION_STATUS + ("REFUNDED",)


def upgrade() -> None:
    # `native_enum=False` renders as VARCHAR + CHECK. Batch mode lets SQLite
    # rebuild the table so the CHECK constraint is refreshed.
    with op.batch_alter_table("actions") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.Enum(
                *OLD_ACTION_STATUS,
                name="action_status",
                native_enum=False,
                length=32,
            ),
            type_=sa.Enum(
                *NEW_ACTION_STATUS,
                name="action_status",
                native_enum=False,
                length=32,
            ),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("actions") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.Enum(
                *NEW_ACTION_STATUS,
                name="action_status",
                native_enum=False,
                length=32,
            ),
            type_=sa.Enum(
                *OLD_ACTION_STATUS,
                name="action_status",
                native_enum=False,
                length=32,
            ),
            existing_nullable=False,
        )
