"""
Shared test fixtures.

Tests use an in-memory SQLite database so they run without a live Postgres.
Because the ORM models use `Enum(..., native_enum=False)` and `JSON` (portable
types), the schema is bit-identical enough for what these tests exercise.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure every model class is registered on Base.metadata before create_all.
import app.models  # noqa: F401
from app.db import Base


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def session(engine) -> Session:
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
