"""HTTP-level integration tests for /runs endpoints.

Uses FastAPI TestClient + DB-rollback session from the root conftest;
seed_agent from tests/runs/conftest.py inserts the agent row that
POST /runs requires.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.runs import service


def _seed_agent_via_client(client, name: str = "T") -> str:
    """POST /agents and return the new agent id."""
    payload = {
        "name": name,
        "system_prompt": "Be helpful",
        "model": {
            "provider": "gemini",
            "name": "gemini-3.1-flash-lite-preview",
        },
    }
    resp = client.post("/agents", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------- POST /runs ----------


def test_post_runs_minimal_valid_payload(client, monkeypatch):
    """POST with minimal valid body → 202 + RunRead in status=pending."""
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)

    resp = client.post("/runs", json={"agent_id": agent_id, "input": "hi"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["agent_id"] == agent_id
    assert body["token_usage_prompt"] == 0
    assert body["token_usage_completion"] == 0
    assert body["cost_usd"] == 0.0
    assert body["step_count"] == 0
    assert body["started_at"] is None
    assert body["completed_at"] is None
    assert body["output"] is None


def test_post_runs_missing_agent_id_returns_422(client):
    resp = client.post("/runs", json={"input": "hi"})
    assert resp.status_code == 422


def test_post_runs_missing_input_returns_422(client):
    resp = client.post("/runs", json={"agent_id": str(uuid4())})
    assert resp.status_code == 422


def test_post_runs_empty_input_returns_422(client):
    resp = client.post(
        "/runs", json={"agent_id": str(uuid4()), "input": ""}
    )
    assert resp.status_code == 422


def test_post_runs_unknown_agent_id_returns_404(client, monkeypatch):
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)

    resp = client.post(
        "/runs", json={"agent_id": str(uuid4()), "input": "hi"}
    )
    assert resp.status_code == 404


def test_post_runs_spawns_wrapper_task(client, monkeypatch):
    """The wrapper is scheduled with the new run id; the HTTP response does
    not wait for run.started to be emitted."""
    import app.runtime.wrapper.service as wrapper_service

    spawned: list = []

    async def fake_run_agent(run_id):
        spawned.append(run_id)

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)

    resp = client.post("/runs", json={"agent_id": agent_id, "input": "hi"})
    assert resp.status_code == 202
    assert len(spawned) == 1
    assert str(spawned[0]) == resp.json()["id"]


# ---------- POST /runs/{id}/cancel ----------


def test_cancel_pending_run_returns_202_and_publishes_event(
    client, monkeypatch, bus_events
):
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)
    created = client.post(
        "/runs", json={"agent_id": agent_id, "input": "hi"}
    )
    run_id = created.json()["id"]

    resp = client.post(f"/runs/{run_id}/cancel")
    assert resp.status_code == 202
    cancel_events = [e for e in bus_events if e.type == "run.cancelled"]
    assert len(cancel_events) == 1
    assert cancel_events[0].payload["run_id"] == run_id
    assert cancel_events[0].payload.get("note") is None


def test_cancel_with_note_carries_note_through_to_payload(
    client, monkeypatch, bus_events
):
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)
    created = client.post(
        "/runs", json={"agent_id": agent_id, "input": "hi"}
    )
    run_id = created.json()["id"]

    resp = client.post(
        f"/runs/{run_id}/cancel", json={"note": "stopping to edit"}
    )
    assert resp.status_code == 202
    cancel_events = [e for e in bus_events if e.type == "run.cancelled"]
    assert cancel_events[0].payload["note"] == "stopping to edit"


def test_cancel_unknown_id_returns_404(client):
    resp = client.post(f"/runs/{uuid4()}/cancel")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "terminal", ["completed", "failed", "aborted", "cancelled"]
)
def test_cancel_terminal_run_returns_409(
    client, db_session, monkeypatch, terminal
):
    """409 response body is RunAlreadyTerminalResponse { status }."""
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)
    created = client.post(
        "/runs", json={"agent_id": agent_id, "input": "hi"}
    )
    run_id = created.json()["id"]

    # Force-transition the row to a terminal state via the service
    from uuid import UUID

    from app.runs.domain import RunStatus

    service.transition_run_state(
        db_session,
        UUID(run_id),
        RunStatus(terminal),
        completed_at=datetime.now(UTC),
    )

    resp = client.post(f"/runs/{run_id}/cancel")
    assert resp.status_code == 409
    detail = resp.json().get("detail", resp.json())
    assert detail["status"] == terminal


# ---------- GET /runs ----------


def test_get_runs_with_no_filters_returns_items_and_total(
    client, monkeypatch
):
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)
    for _ in range(3):
        client.post("/runs", json={"agent_id": agent_id, "input": "hi"})

    resp = client.get("/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_get_runs_filter_by_status(client, monkeypatch, db_session):
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)
    r1 = client.post("/runs", json={"agent_id": agent_id, "input": "a"}).json()
    r2 = client.post("/runs", json={"agent_id": agent_id, "input": "b"}).json()

    from uuid import UUID

    from app.runs.domain import RunStatus

    service.transition_run_state(
        db_session,
        UUID(r1["id"]),
        RunStatus.completed,
        completed_at=datetime.now(UTC),
    )

    resp = client.get("/runs", params={"status": "pending"})
    assert resp.status_code == 200
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert r2["id"] in ids
    assert r1["id"] not in ids


def test_get_runs_filter_by_agent_id(client, monkeypatch):
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_a = _seed_agent_via_client(client, name="A")
    agent_b = _seed_agent_via_client(client, name="B")
    client.post("/runs", json={"agent_id": agent_a, "input": "x"})
    client.post("/runs", json={"agent_id": agent_b, "input": "y"})

    resp = client.get("/runs", params={"agent_id": agent_a})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["agent_id"] == agent_a


def test_get_runs_combined_filters(client, monkeypatch, db_session):
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_a = _seed_agent_via_client(client, name="A")
    agent_b = _seed_agent_via_client(client, name="B")
    client.post("/runs", json={"agent_id": agent_a, "input": "x"})
    client.post("/runs", json={"agent_id": agent_b, "input": "y"})

    resp = client.get(
        "/runs", params={"status": "pending", "agent_id": agent_a}
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["agent_id"] == agent_a


def test_get_runs_pagination_total_ignores_pagination(client, monkeypatch):
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)
    for _ in range(5):
        client.post("/runs", json={"agent_id": agent_id, "input": "hi"})

    resp = client.get("/runs", params={"limit": 2, "offset": 1})
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


def test_get_runs_invalid_status_returns_422(client):
    resp = client.get("/runs", params={"status": "garbage"})
    assert resp.status_code == 422


def test_get_runs_comma_separated_status_returns_422(client):
    """Single value only — not a list. (Status filter chips are single-select.)"""
    resp = client.get("/runs", params={"status": "active,completed"})
    assert resp.status_code == 422


def test_get_runs_uses_settings_default_limit(client, monkeypatch):
    """No ?limit → server returns up to settings.runs_default_list_limit items."""
    from app.settings import settings

    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)
    for _ in range(3):
        client.post("/runs", json={"agent_id": agent_id, "input": "hi"})

    resp = client.get("/runs")
    body = resp.json()
    assert len(body["items"]) <= settings.runs_default_list_limit


def test_get_runs_limit_above_settings_max_returns_422(client):
    from app.settings import settings

    resp = client.get(
        "/runs", params={"limit": settings.runs_max_list_limit + 1}
    )
    assert resp.status_code == 422


def test_get_runs_negative_offset_returns_422(client):
    resp = client.get("/runs", params={"offset": -1})
    assert resp.status_code == 422


# ---------- GET /runs/{id} ----------


def test_get_run_existing_id_returns_200(client, monkeypatch):
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)
    created = client.post(
        "/runs", json={"agent_id": agent_id, "input": "hi"}
    )
    run_id = created.json()["id"]

    resp = client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == run_id
    assert body["status"] == "pending"


def test_get_run_unknown_id_returns_404(client):
    resp = client.get(f"/runs/{uuid4()}")
    assert resp.status_code == 404


# ---------- GET /runs/{id}/events ----------


def test_get_run_events_with_no_events_returns_empty_items(
    client, monkeypatch
):
    import app.runtime.wrapper.service as wrapper_service

    async def fake_run_agent(run_id):
        pass

    monkeypatch.setattr(wrapper_service, "run_agent", fake_run_agent)
    agent_id = _seed_agent_via_client(client)
    created = client.post(
        "/runs", json={"agent_id": agent_id, "input": "hi"}
    )
    run_id = created.json()["id"]

    resp = client.get(f"/runs/{run_id}/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []


def test_get_run_events_unknown_run_returns_404(client):
    resp = client.get(f"/runs/{uuid4()}/events")
    assert resp.status_code == 404
