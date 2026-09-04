"""
Agent authentication for Warden.

Pure Python. No LLM calls, no Razorpay calls, no network. The only I/O is a
single ORM read of the AgentCredential row via the session the caller
provides — never a fresh connection.

Enforced by tests/test_architectural_invariants.py (this file may not import
app.agents, app.payments, anthropic, openai, or razorpay).

Contract:
  - Every proposal from an AI Buyer Agent MUST be signed:
        signature = HMAC-SHA256(secret, canonical_json(proposal_payload))
  - `verify_agent_authorized(session, agent_id, signature_hex, payload)`
    returns AuthResult(ok=True) only if:
      1. an AgentCredential exists for agent_id and is not revoked
      2. the credential is scoped to the mandate the proposal targets
      3. the HMAC verifies exactly (constant-time compare)
  - Any other outcome is an AuthResult(ok=False) with a reason string.
    The coordinator turns that into a BLOCK AGENT_AUTH_FAILED and a
    matching audit event BEFORE the policy engine is called.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent_credential import AgentCredential


# ---- Canonicalization -------------------------------------------------------


def _default(o: Any) -> Any:
    if isinstance(o, Decimal):
        return format(o, "f")
    if hasattr(o, "isoformat"):
        return o.isoformat()
    raise TypeError(f"non-serializable value: {type(o).__name__}")


def canonicalize_proposal(payload: dict[str, Any]) -> bytes:
    """
    Deterministic UTF-8 encoding of the proposal payload for HMAC.
    Same ordering, spacing, and Decimal handling as the audit hash chain,
    so signatures are stable across restarts and languages.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default,
    ).encode("utf-8")


def sign_proposal(secret: str, payload: dict[str, Any]) -> str:
    """HMAC-SHA256 over the canonicalized payload. Returns hex digest."""
    return hmac.new(
        secret.encode("utf-8"), canonicalize_proposal(payload), hashlib.sha256
    ).hexdigest()


def new_secret(nbytes: int = 32) -> str:
    """Cryptographically strong secret for a new agent credential."""
    return secrets.token_hex(nbytes)


# ---- Verification ----------------------------------------------------------


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    reason: str = ""

    @classmethod
    def success(cls) -> "AuthResult":
        return cls(ok=True, reason="")


def verify_agent_authorized(
    session: Session,
    *,
    agent_id: str | None,
    signature_hex: str | None,
    payload: dict[str, Any],
    proposal_mandate_id: str,
) -> AuthResult:
    """
    Verify a proposal was signed by an agent authorized for the mandate.

    Missing agent_id or signature is a definitive BLOCK — callers MUST pass
    both fields (or neither, for the system/direct path handled by the
    coordinator before calling this).
    """
    if not agent_id:
        return AuthResult(ok=False, reason="Missing X-Agent-Id")
    if not signature_hex:
        return AuthResult(ok=False, reason="Missing X-Agent-Signature")

    cred = session.get(AgentCredential, agent_id)
    if cred is None:
        return AuthResult(ok=False, reason=f"Unknown agent {agent_id!r}")
    if cred.revoked_at is not None:
        return AuthResult(ok=False, reason=f"Agent {agent_id!r} has been revoked")

    if cred.mandate_id != proposal_mandate_id:
        # A compromised agent replaying its own valid signature against a
        # different mandate must not succeed.
        return AuthResult(
            ok=False,
            reason=(
                f"Agent {agent_id!r} is scoped to mandate "
                f"{cred.mandate_id!r} but proposal targets {proposal_mandate_id!r}"
            ),
        )

    expected = sign_proposal(cred.secret, payload)
    if not hmac.compare_digest(expected, signature_hex):
        return AuthResult(ok=False, reason="Signature mismatch")

    return AuthResult.success()


# ---- Helpers for creating credentials --------------------------------------


def create_credential(
    session: Session,
    *,
    agent_id: str,
    mandate_id: str,
    secret: str | None = None,
) -> tuple[AgentCredential, str]:
    """
    Register a new credential and return (row, plaintext_secret). Callers
    receive the plaintext once — after this it exists in the DB as-is (see
    the storage note in the model docstring).
    """
    s = secret or new_secret()
    row = AgentCredential(id=agent_id, mandate_id=mandate_id, secret=s)
    session.add(row)
    session.flush()
    return row, s
