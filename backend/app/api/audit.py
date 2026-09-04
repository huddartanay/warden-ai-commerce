"""Audit + resolution HTTP endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import GENESIS_HASH, compute_hash
from app.config import get_settings
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


# ---- DEMO_MODE: tamper endpoints (gated) ----------------------------------
#
# These endpoints deliberately corrupt one audit row so a presenter can
# show live tamper detection by GET /audit/verify. Because they mutate an
# append-only log, they refuse to run unless DEMO_MODE=true is set in the
# environment.
#
# Original payloads are stashed in this module-level dict so a subsequent
# /audit/demo/restore call can undo the corruption. Not persistent across
# restarts — that's fine for a demo.
_DEMO_CORRUPTION_BACKUPS: dict[int, dict[str, object]] = {}


def _require_demo_mode() -> None:
    if not get_settings().demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "DEMO_MODE is not enabled. The audit-tamper endpoints are for "
                "presentations only and refuse to run in normal operation."
            ),
        )


@router.post("/demo/corrupt/{seq}")
def demo_corrupt_endpoint(seq: int, db: Session = Depends(get_db)) -> dict:
    """
    DEMO ONLY: overwrite one audit row's event_data with a tamper marker,
    leaving its stored hashes untouched. The next /audit/verify call must
    then detect the mismatch.
    """
    _require_demo_mode()
    from app.models import AuditLog

    row = db.get(AuditLog, seq)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit row seq={seq} not found.",
        )
    _DEMO_CORRUPTION_BACKUPS[seq] = row.event_data
    row.event_data = {"_demo_corruption": True, "note": "audit row deliberately mutated for demo"}
    db.commit()
    return {
        "corrupted_seq": seq,
        "event_type": row.event_type,
        "message": (
            "Audit row rewritten. Call GET /audit/verify to see the chain "
            "detect the tamper, then POST /audit/demo/restore to revert."
        ),
    }


@router.post("/demo/restore")
def demo_restore_endpoint(db: Session = Depends(get_db)) -> dict:
    """DEMO ONLY: undo every /audit/demo/corrupt performed this session."""
    _require_demo_mode()
    from app.models import AuditLog

    restored = []
    for seq, original in list(_DEMO_CORRUPTION_BACKUPS.items()):
        row = db.get(AuditLog, seq)
        if row is not None:
            row.event_data = original
            restored.append(seq)
        _DEMO_CORRUPTION_BACKUPS.pop(seq, None)
    db.commit()
    return {"restored_seqs": restored}


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
