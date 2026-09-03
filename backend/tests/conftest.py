"""
Shared test fixtures.

Tests use an in-memory SQLite database so they run without a live Postgres.
Because the ORM models use `Enum(..., native_enum=False)` and `JSON` (portable
types), the schema is bit-identical enough for what these tests exercise.
"""

from __future__ import annotations

import os

# Force the LLM into deterministic mock mode BEFORE any app import that reads
# settings. Tests must never hit a real network.
os.environ.setdefault("WARDEN_LLM_MODE", "mock")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure every model class is registered on Base.metadata before create_all.
import app.models  # noqa: F401
from app.db import Base

# Clear the settings cache in case a previous import already resolved it.
from app.config import get_settings

get_settings.cache_clear()


@pytest.fixture
def engine():
    # StaticPool + check_same_thread=False so every connection checked out
    # (including from FastAPI's TestClient threadpool) shares the same
    # in-memory SQLite database.
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
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


@pytest.fixture
def api(engine) -> tuple[TestClient, Session]:
    """
    Yields (client, session) sharing the same in-memory SQLite database.

    The `session` is what tests use for setup (seed rows, assertions).
    The `client` invokes FastAPI routes; its own DB dependency yields the
    same session so writes made through the API are visible to the test
    and vice versa.
    """
    from app.db import get_db
    from app.main import app

    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = SessionLocal()

    def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        client = TestClient(app)
        yield client, session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
