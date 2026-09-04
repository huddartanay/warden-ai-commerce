"""
Resolution-queue service.

An action enters the queue automatically when:
  - Warden returns STEP_UP    -> REQUIRES_HUMAN
  - A payment op has an uncertain outcome -> PENDING_UNRESOLVED

It leaves the queue when:
  - /warden/approve promotes the STEP_UP action (mark_resolved)
  - /audit/resolve is called by a human (mark_resolved + optional side effect)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Resolution, ResolutionStatus


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _new_id() -> str:
    return f"res_{uuid4().hex[:20]}"


def get_by_action(session: Session, action_id: str) -> Resolution | None:
    return session.execute(
        select(Resolution).where(Resolution.action_id == action_id)
    ).scalar_one_or_none()


def upsert_resolution(
    session: Session,
    *,
    action_id: str,
    status: ResolutionStatus,
    note: str = "",
    when: datetime | None = None,
) -> Resolution:
    """
    Create the resolution row if it doesn't exist, or overwrite its status
    + note if it does. Never silently downgrades — a REQUIRES_HUMAN row that
    later becomes PENDING_UNRESOLVED (or vice versa) reflects the new state.
    """
    now = when or _now_utc()
    existing = get_by_action(session, action_id)
    if existing is None:
        row = Resolution(
            id=_new_id(),
            action_id=action_id,
            status=status,
            note=note,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        return row
    existing.status = status
    if note:
        existing.note = note
    existing.updated_at = now
    if status != ResolutionStatus.RESOLVED:
        existing.resolved_by = None
        existing.resolved_at = None
    session.flush()
    return existing


def mark_resolved(
    session: Session,
    *,
    action_id: str,
    resolved_by: str = "system",
    note: str = "",
    when: datetime | None = None,
) -> Resolution | None:
    """
    Move an action's resolution row into RESOLVED. Returns the updated row,
    or None if the action never had a queue entry (that's fine — some ALLOW
    happy paths never enqueue).
    """
    row = get_by_action(session, action_id)
    if row is None:
        return None
    now = when or _now_utc()
    row.status = ResolutionStatus.RESOLVED
    row.resolved_by = resolved_by
    row.resolved_at = now
    if note:
        row.note = note
    row.updated_at = now
    session.flush()
    return row


def list_queue(
    session: Session, *, statuses: Iterable[ResolutionStatus] | None = None
) -> list[Resolution]:
    stmt = select(Resolution)
    if statuses is not None:
        stmt = stmt.where(Resolution.status.in_(list(statuses)))
    stmt = stmt.order_by(Resolution.updated_at.desc())
    return list(session.execute(stmt).scalars().all())
