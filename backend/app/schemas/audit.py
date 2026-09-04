"""Pydantic schemas for the audit + resolution HTTP surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ActionStatus, ResolutionStatus


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    event_id: str
    action_id: str | None
    event_type: str
    event_data: dict[str, Any]
    previous_hash: str
    current_hash: str
    timestamp: datetime


class AuditListResponse(BaseModel):
    count: int
    entries: list[AuditEntryOut]


class AuditVerifyResponse(BaseModel):
    valid: bool
    entries_checked: int
    first_invalid_entry: dict[str, Any] | None = None


class ResolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action_id: str
    status: ResolutionStatus
    note: str
    resolved_by: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResolutionListResponse(BaseModel):
    count: int
    entries: list[ResolutionOut]


class ResolveRequest(BaseModel):
    # Optional: the human's final take. Must be one of PAYMENT_COMPLETED,
    # PAYMENT_FAILED, or REFUNDED for PENDING_UNRESOLVED actions. Omit to
    # simply mark the resolution row RESOLVED without changing the action's
    # own status.
    new_action_status: ActionStatus | None = None
    note: str = Field(default="")
    resolved_by: str = Field(default="human")


class ResolveResponse(BaseModel):
    resolution: ResolutionOut
    action_status: ActionStatus