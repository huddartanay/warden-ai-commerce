"""Append-only, hash-chained audit log service."""

from app.audit import events
from app.audit.hash_chain import GENESIS_HASH, canonicalize, compute_hash
from app.audit.service import append_event, verify_chain

__all__ = [
    "GENESIS_HASH",
    "append_event",
    "canonicalize",
    "compute_hash",
    "events",
    "verify_chain",
]
