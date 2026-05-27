"""
Test harness fixtures for yuno backend.

Strategy:
- DB: real Postgres + transactional rollback per test. A session-scoped fixture
  creates a separate `yuno_test` database, runs SQLModel.metadata.create_all,
  then each test runs inside a connection-level transaction rolled back at teardown.
- LLM: `mock_llm` monkeypatches litellm.completion to return canned ModelResponse
  shapes. CrewAI's orchestration and callback machinery still run real.
- Event bus: `bus_events` monkeypatches bus.publish to record every event for
  assertion.
- FastAPI: `client` wires a TestClient with get_session overridden to the test
  session, so endpoint reads/writes share the test's transaction.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

# Import the model registry so SQLModel.metadata is populated before
# metadata.create_all runs in the `engine` fixture.
from app import models  # noqa: F401, E402

ADMIN_URL = os.getenv(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql+psycopg://yuno:yuno@postgres:5432/postgres",
)
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "yuno_test")
TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql+psycopg://yuno:yuno@postgres:5432/{TEST_DB_NAME}",
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_database() -> Iterator[None]:
    """Create yuno_test database if missing. Idempotent across runs."""
    admin = sa_create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"),
            {"n": TEST_DB_NAME},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()
    yield


@pytest.fixture(scope="session")
def engine():
    """Session-scoped engine bound to the test database, with schema created."""
    eng = create_engine(TEST_URL, echo=False, pool_pre_ping=True)
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Iterator[Session]:
    """Per-test session inside a transaction that rolls back at teardown.

    Uses SQLAlchemy 2.x `join_transaction_mode="create_savepoint"` so any
    `session.commit()` inside endpoint handlers creates/releases SAVEPOINTs
    instead of committing the outer transaction. The outer rollback wipes
    everything on teardown.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """FastAPI TestClient with get_session overridden to share the test session."""
    from app.db import get_session
    from app.main import app

    def _override() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch):
    """Mock litellm.completion. CrewAI's Agent/Task/Crew run real on top of this.

    Returns a MagicMock whose `.return_value` can be reassigned per test via
    `mock_llm.set_response(content=..., prompt_tokens=..., completion_tokens=...)`.
    """
    import litellm  # noqa: PLC0415  (lazy to keep import-time cheap)
    from litellm.types.utils import Choices, Message, ModelResponse, Usage

    def make_response(
        content: str = "ok",
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
        model: str = "gemini/gemini-3.1-flash-lite-preview",
    ) -> ModelResponse:
        return ModelResponse(
            id="test-completion",
            choices=[
                Choices(
                    index=0,
                    message=Message(content=content, role="assistant"),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            model=model,
        )

    mock = MagicMock(side_effect=lambda *a, **kw: make_response())
    mock.make_response = make_response

    def set_response(**kwargs: Any) -> None:
        mock.side_effect = lambda *a, **kw: make_response(**kwargs)

    mock.set_response = set_response

    monkeypatch.setattr(litellm, "completion", mock)
    return mock


@pytest.fixture
def bus_events(monkeypatch: pytest.MonkeyPatch) -> list:
    """Capture every event published on the in-process bus during a test.

    Returns a list that's appended to in-order as events are published.
    The original `publish` still runs, so subscribers still fire.
    """
    from app import event_bus as eb

    captured: list = []
    original_publish = eb.bus.publish

    async def capturing_publish(event) -> None:
        captured.append(event)
        await original_publish(event)

    monkeypatch.setattr(eb.bus, "publish", capturing_publish)
    return captured
