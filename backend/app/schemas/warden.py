"""Pydantic request/response contracts for the Warden API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ActionStatus, DecisionResult, MandateStatus, ReasonCode


# ---- Warden evaluate --------------------------------------------------------


class EvaluateRequest(BaseModel):
    """The typed payment proposal submitted for Warden evaluation."""

    mandate_id: str
    customer_id: str
    merchant_id: str
    cart_id: str
    amount: Decimal = Field(..., ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    category: str
    quoted_price: Decimal = Field(..., ge=0)
    current_price: Decimal = Field(..., ge=0)
    idempotency_key: str = Field(..., min_length=1, max_length=64)
    action_id: str | None = None  # optional; server generates if omitted


class CheckResultOut(BaseModel):
    name: str
    ok: bool
    verdict: Literal["PASS", "STEP_UP", "BLOCK"]
    reason_code: ReasonCode | None = None
    detail: str


class DecisionResponse(BaseModel):
    action_id: str
    decision: DecisionResult
    reason_code: ReasonCode
    explanation: str
    checks_performed: list[CheckResultOut]
    duplicate: bool = False


# ---- Mandate + action read --------------------------------------------------


class MandateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    merchant_id: str
    max_amount: Decimal
    currency: str
    allowed_categories: list[str]
    transaction_limit: int
    validity_start: datetime
    validity_end: datetime
    status: MandateStatus
    current_period_spend: Decimal
    current_period_transactions: int
    step_up_over_amount: Decimal | None
    created_at: datetime
    updated_at: datetime


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action_id: str
    result: DecisionResult
    reason_code: ReasonCode
    explanation: str
    created_at: datetime


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mandate_id: str
    cart_id: str | None
    action_type: str
    amount: Decimal
    currency: str
    idempotency_key: str
    status: ActionStatus
    created_at: datetime
    updated_at: datetime


class ActionDetail(BaseModel):
    action: ActionOut
    decision: DecisionOut | None
