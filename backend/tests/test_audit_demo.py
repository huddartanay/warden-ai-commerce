"""
Stage 7 (4/4) — DEMO_MODE audit-tamper endpoints.

Regardless of DEMO_MODE, GET /audit/verify already detects tampering
(covered by test_audit_verify_detects_tampering in test_audit_api.py).
Here we prove:

- With DEMO_MODE off, /audit/demo/* returns 403.
- With DEMO_MODE on, corrupt+verify+restore work as a full demo loop.
"""

from __future__ import annotations

import pytest

from app.audit import verify_chain
from app.config import get_settings
from app.models import AuditLog
from app.seed import seed_data


def _seeded(session):
    seed_data(session)
    session.commit()


def _reload_settings():
    get_settings.cache_clear()
    return get_settings()


# ---- Without DEMO_MODE ----------------------------------------------------


def test_demo_endpoints_forbidden_when_demo_mode_off(api, monkeypatch):
    """
    Explicitly disable DEMO_MODE and confirm the tamper routes refuse to run.
    Uses monkeypatch so the change doesn't leak to other tests.
    """
    client, session = api
    _seeded(session)
    monkeypatch.setenv("DEMO_MODE", "false")
    _reload_settings()

    seq = session.query(AuditLog).first().seq

    r = client.post(f"/audit/demo/corrupt/{seq}")
    assert r.status_code == 403
    assert "DEMO_MODE" in r.json()["detail"]

    r = client.post("/audit/demo/restore")
    assert r.status_code == 403


# ---- With DEMO_MODE on ----------------------------------------------------


@pytest.fixture
def api_demo_mode(api, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    _reload_settings()
    try:
        yield api
    finally:
        monkeypatch.setenv("DEMO_MODE", "false")
        _reload_settings()


def test_corrupt_then_verify_detects_and_restore_repairs(api_demo_mode):
    client, session = api_demo_mode
    _seeded(session)

    target_seq = session.query(AuditLog).order_by(AuditLog.seq.asc()).first().seq

    # Chain is clean before we start.
    r = client.get("/audit/verify").json()
    assert r["valid"] is True

    # Corrupt.
    r = client.post(f"/audit/demo/corrupt/{target_seq}")
    assert r.status_code == 200
    assert r.json()["corrupted_seq"] == target_seq

    # Verify now detects it.
    r = client.get("/audit/verify").json()
    assert r["valid"] is False
    assert r["first_invalid_entry"]["seq"] == target_seq
    assert r["first_invalid_entry"]["reason"] == "current_hash_mismatch"

    # Restore.
    r = client.post("/audit/demo/restore")
    assert r.status_code == 200
    assert target_seq in r.json()["restored_seqs"]

    # Chain is clean again.
    r = client.get("/audit/verify").json()
    assert r["valid"] is True

    # And verify_chain agrees at the ORM level.
    ok, reason = verify_chain(session)
    assert ok is True, reason


def test_corrupt_nonexistent_seq_returns_404(api_demo_mode):
    client, session = api_demo_mode
    _seeded(session)
    r = client.post("/audit/demo/corrupt/999999")
    assert r.status_code == 404
