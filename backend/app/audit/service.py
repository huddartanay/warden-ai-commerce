"""
Audit writer + verifier.

`append_event` is the only supported way to write to the audit log. It:
  1. reads the current tail hash (or GENESIS_HASH if empty),
  2. computes the new current_hash deterministically,
  3. inserts the row inside the caller's session.

`verify_chain` walks the whole log and recomputes each hash to detect tampering.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.hash_chain import GENESIS_HASH, compute_hash
from app.models.audit import AuditLog


def _new_event_id() -> str:
    return f"evt_{uuid4().hex[:20]}"


def _tail_hash(session: Session) -> str:
    row = session.execute(
        select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)
    ).scalar_one_or_none()
    return row.current_hash if row is not None else GENESIS_HASH


def append_event(
    session: Session,
    *,
    event_type: str,
    event_data: dict,
    action_id: str | None = None,
    event_id: str | None = None,
    timestamp: datetime | None = None,
) -> AuditLog:
    """Append one event to the audit log. Caller controls the session/transaction."""
    prev = _tail_hash(session)
    curr = compute_hash(prev, event_type, event_data)
    row = AuditLog(
        event_id=event_id or _new_event_id(),
        action_id=action_id,
        event_type=event_type,
        event_data=event_data,
        previous_hash=prev,
        current_hash=curr,
        timestamp=timestamp or datetime.now(tz=timezone.utc),
    )
    session.add(row)
    session.flush()
    return row


def verify_chain(session: Session) -> tuple[bool, str | None]:
    """
    Walk the audit log in seq order and re-derive each hash.
    Returns (True, None) if the chain is intact, else (False, reason).
    """
    prev = GENESIS_HASH
    rows = session.execute(select(AuditLog).order_by(AuditLog.seq.asc())).scalars().all()
    for row in rows:
        if row.previous_hash != prev:
            return False, f"previous_hash mismatch at seq={row.seq}"
        expected = compute_hash(prev, row.event_type, row.event_data)
        if row.current_hash != expected:
            return False, f"current_hash mismatch at seq={row.seq}"
        prev = row.current_hash
    return True, None
