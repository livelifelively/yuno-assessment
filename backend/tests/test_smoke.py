"""
Smoke tests verify the harness itself: DB fixture, FastAPI client, mock_llm,
bus_events. If any of these break, every later test will too — so they go first.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, text


def test_health_endpoint(client: TestClient) -> None:
    """FastAPI client fixture wires the app correctly."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_system_endpoint(client: TestClient) -> None:
    """System endpoint returns expected shape (no auth, no DB needed)."""
    response = client.get("/system")
    assert response.status_code == 200
    body = response.json()
    assert "app_env" in body
    assert "crewai" in body
    assert "providers_configured" in body


def test_db_session_executes_query(db_session: Session) -> None:
    """DB fixture connects to the test database and runs SQL."""
    result = db_session.execute(text("SELECT 1 AS one")).scalar()
    assert result == 1


def test_db_session_isolates_writes(db_session: Session) -> None:
    """Writes in one test should not leak to the next test (rollback verification).

    This test pairs with test_db_session_no_leak below. We create a temp table
    and insert a row; the next test asserts the table does not exist.
    """
    db_session.execute(text("CREATE TABLE smoke_leak_check (n INTEGER)"))
    db_session.execute(text("INSERT INTO smoke_leak_check (n) VALUES (42)"))
    db_session.commit()
    count = db_session.execute(text("SELECT COUNT(*) FROM smoke_leak_check")).scalar()
    assert count == 1


def test_db_session_no_leak(db_session: Session) -> None:
    """Verifies the previous test's table does NOT survive — rollback works."""
    exists = db_session.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'smoke_leak_check')"
        )
    ).scalar()
    assert exists is False


def test_mock_llm_default_response(mock_llm) -> None:
    """mock_llm returns a canned ModelResponse with usage block."""
    import litellm

    response = litellm.completion(model="gemini/test", messages=[])
    assert response.choices[0].message.content == "ok"
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 5
    assert response.usage.total_tokens == 15


def test_mock_llm_custom_response(mock_llm) -> None:
    """set_response lets a test override the canned response per-test."""
    import litellm

    mock_llm.set_response(content="hello world", prompt_tokens=3, completion_tokens=2)
    response = litellm.completion(model="gemini/test", messages=[])
    assert response.choices[0].message.content == "hello world"
    assert response.usage.total_tokens == 5


@pytest.mark.asyncio
async def test_bus_events_captures_publishes(bus_events: list) -> None:
    """bus_events captures every event published during the test."""
    from app.event_bus import Event, bus

    await bus.publish(Event(type="test.one", payload={"k": 1}))
    await bus.publish(Event(type="test.two", payload={"k": 2}))

    assert len(bus_events) == 2
    assert bus_events[0].type == "test.one"
    assert bus_events[0].payload == {"k": 1}
    assert bus_events[1].type == "test.two"
