"""
Pure functions for the audit hash chain.

current_hash = SHA256(previous_hash || event_type || canonical_json(event_data))

The event_type is folded into the hash so two events with the same payload but
different types (e.g. ALLOW vs BLOCK carrying the same body) can never collide.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

GENESIS_HASH = "0" * 64
_HASH_SEP = "|"


def _default(o: Any) -> Any:
    if isinstance(o, Decimal):
        # Preserve exact string form to avoid float rounding drift.
        return format(o, "f")
    # datetime / date fall through to isoformat via __str__ below.
    if hasattr(o, "isoformat"):
        return o.isoformat()
    raise TypeError(f"non-serializable value: {type(o).__name__}")


def canonicalize(event_data: dict) -> str:
    """Deterministic JSON encoding: sorted keys, no whitespace, stable Decimal."""
    return json.dumps(
        event_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default,
    )


def compute_hash(previous_hash: str, event_type: str, event_data: dict) -> str:
    payload = f"{previous_hash}{_HASH_SEP}{event_type}{_HASH_SEP}{canonicalize(event_data)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
