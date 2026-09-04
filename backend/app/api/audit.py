"""Audit + resolution HTTP endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import GENESIS_HASH, compute_hash
from app.db import get_db
from app.models import Action, AuditLog, ResolutionStatus
from app.schemas.audit import (
    AuditEntryOut,
    AuditListResponse,
    AuditVerifyResponse,
    ResolutionListResponse,
    ResolutionOut,
    ResolveRequest,
    ResolveResponse,
)
from app.services.resolution import get_by_action, list_queue
from app.warden import (
    ActionNotFoundError,
    InvalidActionStateError,
    resolve_pending_action,
)

router = APIRouter(prefix="/audit", tags=["audit"])


# ---- Reads ----------------------------------------------------------------


@router.get("/action/{action_id}", response_model=AuditListResponse)
def audit_by_action(action_id: str, db: Session = Depends(get_db)) -> AuditListResponse:
    """All audit entries mentioning this action, in sequence order."""
    rows = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.action_id == action_id)
            .order_by(AuditLog.seq.asc())
        )
        .scalars()
        .all()
    )
    return AuditListResponse(
        count=len(rows),
        entries=[AuditEntryOut.model_validate(r) for r in rows],
    )


@router.get("/mandate/{mandate_id}", response_model=AuditListResponse)
def audit_by_mandate(mandate_id: str, db: Session = Depends(get_db)) -> AuditListResponse:
    """
    All audit entries tied to this mandate. Includes entries linked via
    action_id (the action's mandate matches) and entries where event_data
    itself carries the mandate_id (e.g. MANDATE_CREATED, MANDATE_REVOKED).
    """
    action_ids = set(
        db.execute(
            select(Action.id).where(Action.mandate_id == mandate_id)
        )
        .scalars()
        .all()
    )
    rows = (
        db.execute(select(AuditLog).order_by(AuditLog.seq.asc())).scalars().all()
    )
    matched = [
        r
        for r in rows
        if (r.action_id in action_ids)
        or (r.event_data and r.event_data.get("mandate_id") == mandate_id)
    ]
    return AuditListResponse(
        count=len(matched),
        entries=[AuditEntryOut.model_validate(r) for r in matched],
    )


@router.get("/verify", response_model=AuditVerifyResponse)
def audit_verify(db: Session = Depends(get_db)) -> AuditVerifyResponse:
    """
    Recompute every hash in the chain and return the first broken link (if any).
    """
    rows = db.execute(select(AuditLog).order_by(AuditLog.seq.asc())).scalars().all()

    prev = GENESIS_HASH
    for row in rows:
        if row.previous_hash != prev:
            return AuditVerifyResponse(
                valid=False,
                entries_checked=len(rows),
                first_invalid_entry={
                    "seq": row.seq,
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "reason": "previous_hash_mismatch",
                    "expected_previous_hash": prev,
                    "actual_previous_hash": row.previous_hash,
                },
            )
        expected = compute_hash(prev, row.event_type, row.event_data)
        if row.current_hash != expected:
            return AuditVerifyResponse(
                valid=False,
                entries_checked=len(rows),
                first_invalid_entry={
                    "seq": row.seq,
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "reason": "current_hash_mismatch",
                    "expected_current_hash": expected,
                    "actual_current_hash": row.current_hash,
                },
            )
        prev = row.current_hash

    return AuditVerifyResponse(
        valid=True, entries_checked=len(rows), first_invalid_entry=None
    )


# ---- Resolution queue -----------------------------------------------------


@router.get("/resolution-queue", response_model=ResolutionListResponse)
def resolution_queue_endpoint(
    db: Session = Depends(get_db),
    status_filter: ResolutionStatus | None = Query(
        default=None,
        alias="status",
        description="Filter by resolution status. Omit for all.",
    ),
) -> ResolutionListResponse:
    statuses = [status_filter] if status_filter is not None else None
    rows = list_queue(db, statuses=statuses)
    return ResolutionListResponse(
        count=len(rows),
        entries=[ResolutionOut.model_validate(r) for r in rows],
    )


@router.post("/resolve/{action_id}", response_model=ResolveResponse)
def resolve_endpoint(
    action_id: str, body: ResolveRequest, db: Session = Depends(get_db)
) -> ResolveResponse:
    """
    Human-driven resolution of a PENDING_UNRESOLVED action. Optionally moves
    the action to PAYMENT_COMPLETED / PAYMENT_FAILED / REFUNDED. Rolls back
    the mandate reservation on FAILED / REFUNDED.
    """
    try:
        action = resolve_pending_action(
            db,
            action_id,
            new_status=body.new_action_status,
            note=body.note,
            resolved_by=body.resolved_by,
        )
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidActionStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    db.commit()

    row = get_by_action(db, action_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Resolution row disappeared after mark_resolved.",
        )

    return ResolveResponse(
        resolution=ResolutionOut.model_validate(row),
        action_status=action.status,
    )
