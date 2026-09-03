"""Initial Warden schema — 8 tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-09-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MANDATE_STATUS = ("ACTIVE", "PARTIALLY_USED", "EXHAUSTED", "EXPIRED", "REVOKED")
ACTION_TYPE = ("PAYMENT", "REFUND")
ACTION_STATUS = (
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
DECISION_RESULT = ("ALLOW", "STEP_UP", "BLOCK")
REASON_CODE = (
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


def upgrade() -> None:
    op.create_table(
        "merchants",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "catalog_items",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.String(length=64),
            sa.ForeignKey("merchants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "mandates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("customer_id", sa.String(length=64), nullable=False, index=True),
        sa.Column(
            "merchant_id",
            sa.String(length=64),
            sa.ForeignKey("merchants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("max_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("allowed_categories", sa.JSON(), nullable=False),
        sa.Column("transaction_limit", sa.Integer(), nullable=False),
        sa.Column("validity_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validity_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*MANDATE_STATUS, name="mandate_status", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("current_period_spend", sa.Numeric(14, 2), nullable=False),
        sa.Column("current_period_transactions", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "carts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "mandate_id",
            sa.String(length=64),
            sa.ForeignKey("mandates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "merchant_id",
            sa.String(length=64),
            sa.ForeignKey("merchants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "actions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "mandate_id",
            sa.String(length=64),
            sa.ForeignKey("mandates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cart_id",
            sa.String(length=64),
            sa.ForeignKey("carts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "action_type",
            sa.Enum(*ACTION_TYPE, name="action_type", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column(
            "status",
            sa.Enum(*ACTION_STATUS, name="action_status", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "decisions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "action_id",
            sa.String(length=64),
            sa.ForeignKey("actions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "result",
            sa.Enum(*DECISION_RESULT, name="decision_result", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column(
            "reason_code",
            sa.Enum(*REASON_CODE, name="reason_code", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column(
            "seq",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("event_id", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column(
            "action_id",
            sa.String(length=64),
            sa.ForeignKey("actions.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("event_data", sa.JSON(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("current_hash", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    op.create_table(
        "razorpay_refs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "action_id",
            sa.String(length=64),
            sa.ForeignKey("actions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("ref_type", sa.String(length=32), nullable=False),
        sa.Column("razorpay_id", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("razorpay_refs")
    op.drop_table("audit_log")
    op.drop_table("decisions")
    op.drop_table("actions")
    op.drop_table("carts")
    op.drop_table("mandates")
    op.drop_table("catalog_items")
    op.drop_table("merchants")
