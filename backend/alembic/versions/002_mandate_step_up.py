"""Add mandates.step_up_over_amount.

Revision ID: 002_mandate_step_up
Revises: 001_initial
Create Date: 2026-09-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_mandate_step_up"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("mandates") as batch:
        batch.add_column(sa.Column("step_up_over_amount", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mandates") as batch:
        batch.drop_column("step_up_over_amount")
