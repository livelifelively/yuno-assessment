"""Per-package fixtures and helpers for runs tests.

`runs_subscriber` registers a RunsEventSubscriber on the in-process bus for
the test and unregisters at teardown. State-machine / event-persistence
tests use it to route published events through the subscriber pipeline.

`seed_agent` is a small fixture that inserts a minimal AgentRow and returns
its id — runs.create_run validates agent_id against the agents table, so
the test needs an agent to point at.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session

from app.agents.persistence.row import AgentRow
from app.event_bus import bus as global_bus
from app.runs.event_bus.subscriber import RunsEventSubscriber


@pytest.fixture
def runs_subscriber(db_session: Session) -> Iterator[RunsEventSubscriber]:
    """Subscribe a RunsEventSubscriber to the global bus for the test.

    Injects a session factory that yields the test's `db_session` (the same
    one the test uses for writes/reads) without closing it — so the
    subscriber's UPDATE sits in the same savepoint chain as the test's
    other writes, and the test can observe the row state via the same
    session afterwards.
    """

    @contextmanager
    def _factory() -> Iterator[Session]:
        # Yield without entering/exiting the session's own context manager —
        # the test owns the session's lifetime.
        yield db_session

    sub = RunsEventSubscriber(session_factory=_factory)
    sub.register(global_bus)
    try:
        yield sub
    finally:
        sub.unregister(global_bus)


@pytest.fixture
def seed_agent(db_session: Session):
    """Insert a minimal AgentRow and return its id. The runs flow requires
    a real agent for create_run's agent-id validation step."""

    def _seed(**overrides: Any) -> UUID:
        """Insert an AgentRow with sensible defaults; overrides patch fields a test cares about."""
        now = datetime.now(UTC)
        defaults: dict[str, Any] = dict(
            id=uuid4(),
            name="Seeded Agent",
            system_prompt="Be helpful.",
            model_provider="gemini",
            model_name="gemini-3.1-flash-lite-preview",
            created_at=now,
            updated_at=now,
        )
        defaults.update(overrides)
        row = AgentRow(**defaults)
        db_session.add(row)
        db_session.commit()
        db_session.refresh(row)
        return row.id

    return _seed
