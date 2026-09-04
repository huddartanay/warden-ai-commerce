"""
Concurrency tests for the atomic spend-cap enforcement.

Uses a file-backed SQLite (not :memory:) so multiple worker threads can each
hold their own connection against the SAME database. Every worker runs a
full evaluate_proposal + commit for a distinct idempotency_key against ONE
shared mandate whose remaining cap only permits one winner.
"""

from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  register mappers
from app.db import Base
from app.models import Action, ActionStatus, Mandate, MandateStatus
from app.models.enums import DecisionResult, ReasonCode
from app.seed import seed_data
from app.warden import Proposal, evaluate_proposal


@pytest.fixture
def file_db():
    """
    File-backed SQLite engine + session factory so threads share the DB.
    Cleaned up after the test.
    """
    fd, path = tempfile.mkstemp(suffix=".warden_concurrency.db")
    os.close(fd)
    url = f"sqlite:///{path}"
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 10.0},
        future=True,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    try:
        yield engine, SessionLocal
    finally:
        engine.dispose()
        try:
            os.unlink(path)
        except OSError:
            pass


def _tight_mandate_session(SessionLocal) -> None:
    """
    Seed the DB, then dial mandate A down to cap=₹1000 and tx_limit=10 so a
    single ₹1000 proposal exhausts the cap and only one of many concurrent
    proposals can win.
    """
    with SessionLocal() as s:
        seed_data(s)
        mandate = s.get(Mandate, "man_A_regular_2k")
        mandate.max_amount = Decimal("1000.00")
        mandate.transaction_limit = 10  # so tx_limit isn't the reason we BLOCK
        s.commit()


def _propose(SessionLocal, i: int) -> tuple[str, str, DecisionResult, ReasonCode]:
    """One worker: fresh session, submit proposal, commit, return the verdict."""
    with SessionLocal() as s:
        proposal = Proposal(
            mandate_id="man_A_regular_2k",
            customer_id="cust_priya_regular",
            merchant_id="mer_priya_coffee",
            cart_id=f"cart_race_{i}",
            amount=Decimal("1000.00"),
            currency="INR",
            category="coffee",
            quoted_price=Decimal("1000.00"),
            current_price=Decimal("1000.00"),
            idempotency_key=f"race_{i}",
        )
        outcome = evaluate_proposal(s, proposal)
        s.commit()
        return outcome.action_id, f"race_{i}", outcome.decision, outcome.reason_code


def test_concurrent_proposals_cannot_double_spend_cap(file_db):
    """
    N=8 concurrent proposals each attempt to spend the entire remaining cap
    (₹1000). Exactly ONE must be ALLOWed, the rest must BLOCK. None may
    STEP_UP, none may silently succeed twice.
    """
    engine, SessionLocal = file_db
    _tight_mandate_session(SessionLocal)

    N = 8
    with ThreadPoolExecutor(max_workers=N) as pool:
        results = list(pool.map(lambda i: _propose(SessionLocal, i), range(N)))

    decisions = [r[2] for r in results]
    reasons = [r[3] for r in results]

    allow_count = decisions.count(DecisionResult.ALLOW)
    block_count = decisions.count(DecisionResult.BLOCK)
    stepup_count = decisions.count(DecisionResult.STEP_UP)

    assert allow_count == 1, (
        f"Exactly one proposal must win. Got {allow_count} ALLOWs, "
        f"{block_count} BLOCKs, {stepup_count} STEP_UPs."
    )
    assert stepup_count == 0
    assert block_count == N - 1

    # Every losing proposal must have a defensible block reason.
    for r in reasons:
        if r == ReasonCode.OK:
            continue
        assert r in {ReasonCode.CAP_EXCEEDED, ReasonCode.CONCURRENT_UPDATE}, r

    # DB state: the mandate holds exactly ONE ALLOW's worth of spend + 1 tx.
    with SessionLocal() as s:
        mandate = s.get(Mandate, "man_A_regular_2k")
        assert mandate.current_period_spend == Decimal("1000.00")
        assert mandate.current_period_transactions == 1
        assert mandate.version >= 1
        assert mandate.status == MandateStatus.EXHAUSTED

        # ...and exactly ONE Action row is in ALLOWED state.
        allowed = s.scalar(
            select(func.count())
            .select_from(Action)
            .where(Action.status == ActionStatus.ALLOWED)
        )
        assert allowed == 1
