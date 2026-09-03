"""Audit hash chain: determinism, chaining, verification, tamper detection."""

from decimal import Decimal

from sqlalchemy import select

from app.audit import (
    GENESIS_HASH,
    append_event,
    canonicalize,
    compute_hash,
    verify_chain,
)
from app.models import AuditLog


def test_canonicalize_is_key_order_independent():
    a = canonicalize({"b": 1, "a": 2})
    b = canonicalize({"a": 2, "b": 1})
    assert a == b == '{"a":2,"b":1}'


def test_canonicalize_handles_decimal_without_float_rounding():
    s = canonicalize({"amount": Decimal("1499.99")})
    assert s == '{"amount":"1499.99"}'


def test_compute_hash_is_deterministic():
    h1 = compute_hash(GENESIS_HASH, "X", {"a": 1})
    h2 = compute_hash(GENESIS_HASH, "X", {"a": 1})
    assert h1 == h2
    assert len(h1) == 64


def test_compute_hash_folds_event_type():
    # Same payload, different type -> different hash.
    same_data = {"foo": "bar"}
    assert compute_hash(GENESIS_HASH, "ALLOW", same_data) != compute_hash(
        GENESIS_HASH, "BLOCK", same_data
    )


def test_append_event_chains_from_genesis(session):
    e1 = append_event(session, event_type="A", event_data={"n": 1})
    assert e1.previous_hash == GENESIS_HASH
    assert e1.current_hash == compute_hash(GENESIS_HASH, "A", {"n": 1})

    e2 = append_event(session, event_type="B", event_data={"n": 2})
    assert e2.previous_hash == e1.current_hash
    assert e2.current_hash == compute_hash(e1.current_hash, "B", {"n": 2})

    e3 = append_event(session, event_type="C", event_data={"n": 3})
    assert e3.previous_hash == e2.current_hash
    session.commit()

    rows = session.execute(select(AuditLog).order_by(AuditLog.seq.asc())).scalars().all()
    assert [r.event_type for r in rows] == ["A", "B", "C"]


def test_verify_chain_accepts_valid_chain(session):
    append_event(session, event_type="X", event_data={"i": 1})
    append_event(session, event_type="Y", event_data={"i": 2})
    append_event(session, event_type="Z", event_data={"i": 3})
    session.commit()

    ok, reason = verify_chain(session)
    assert ok is True
    assert reason is None


def test_verify_chain_detects_data_tampering(session):
    append_event(session, event_type="X", event_data={"i": 1})
    e2 = append_event(session, event_type="Y", event_data={"i": 2})
    append_event(session, event_type="Z", event_data={"i": 3})
    session.commit()

    # Tamper: mutate the middle event's payload but leave its hash intact.
    e2.event_data = {"i": 99}
    session.flush()

    ok, reason = verify_chain(session)
    assert ok is False
    assert reason is not None and "seq=" in reason


def test_verify_chain_detects_broken_previous_hash(session):
    append_event(session, event_type="X", event_data={"i": 1})
    e2 = append_event(session, event_type="Y", event_data={"i": 2})
    session.commit()

    e2.previous_hash = "0" * 64  # break the link
    session.flush()

    ok, reason = verify_chain(session)
    assert ok is False
    assert reason is not None and "previous_hash mismatch" in reason


def test_empty_chain_verifies(session):
    ok, reason = verify_chain(session)
    assert ok is True
    assert reason is None
