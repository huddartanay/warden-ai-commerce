"""Pydantic schemas for the agent HTTP API."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import DecisionResult, ReasonCode


# ---- /agent/purchase-intent -------------------------------------------------


class PurchaseIntentRequest(BaseModel):
    natural_language: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)
    mandate_id: str | None = None
    idempotency_key: str = Field(..., min_length=1, max_length=64)


class PurchaseIntentResponse(BaseModel):
    intent_text: str
    parsed_intent: dict[str, Any] | None
    mandate: dict[str, Any] | None
    candidates: list[dict[str, Any]]
    selected: list[dict[str, Any]]
    quote: dict[str, Any] | None
    cart_id: str | None
    warden: dict[str, Any] | None
    agent_confidence: float
    agent_verdict: DecisionResult
    explanation: str


# ---- /agent/search ---------------------------------------------------------


class SearchRequest(BaseModel):
    merchant_id: str
    query: str | None = None
    category: str | None = None
    max_price: Decimal | None = Field(default=None, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class SearchResponse(BaseModel):
    merchant_id: str
    products: list[dict[str, Any]]


# ---- /agent/build-cart -----------------------------------------------------


class BuildCartItem(BaseModel):
    catalog_item_id: str
    quantity: int = Field(..., ge=1)


class BuildCartRequest(BaseModel):
    customer_id: str
    mandate_id: str | None = None
    items: list[BuildCartItem] = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1, max_length=64)
    # Optional: what the caller believes each item's price was when it proposed
    # the cart. If omitted, we use current catalog prices for both sides so
    # price_drift never fails on this path.
    quoted_prices: dict[str, Decimal] | None = None


# ---- /agent/explain --------------------------------------------------------


class ExplainRequest(BaseModel):
    action_id: str | None = None
    result: DecisionResult | None = None
    reason_code: ReasonCode | None = None
    warden_explanation: str | None = None


class ExplainResponse(BaseModel):
    action_id: str | None
    result: DecisionResult
    reason_code: ReasonCode
    natural_language: str
    warden_explanation: str
