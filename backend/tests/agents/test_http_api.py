"""HTTP-level integration tests for /agents endpoints.

Uses the FastAPI TestClient + the DB-rollback session from conftest. The runs
lock dependency is monkeypatched at app.runs.service.list_active_runs_for_agent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.runs import service as runs_service
from app.runs.domain import ActiveStatus, RunRef


def _create_payload(**overrides) -> dict:
    """Build a minimal valid POST /agents body; overrides set just the fields
    a test cares about."""
    payload = {
        "name": "Test",
        "system_prompt": "Be helpful",
        "model": {
            "provider": "gemini",
            "name": "gemini-3.1-flash-lite-preview",
        },
    }
    payload.update(overrides)
    return payload


# ---------- POST /agents ----------


def test_post_agents_minimal_valid_payload_returns_201(client):
    """POST with the minimal valid body returns 201 plus the persisted agent."""
    resp = client.post("/agents", json=_create_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Test"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_post_agents_missing_name_returns_422(client):
    """Missing required top-level field returns 422."""
    payload = _create_payload()
    del payload["name"]
    resp = client.post("/agents", json=payload)
    assert resp.status_code == 422


def test_post_agents_missing_model_provider_returns_422(client):
    """Missing required nested field (model.provider) returns 422."""
    resp = client.post("/agents", json=_create_payload(model={"name": "m"}))
    assert resp.status_code == 422


def test_post_agents_invalid_provider_returns_422(client):
    """A provider value outside the Provider enum returns 422."""
    resp = client.post(
        "/agents", json=_create_payload(model={"provider": "claude-x", "name": "m"})
    )
    assert resp.status_code == 422


def test_post_agents_invalid_tone_returns_422(client):
    """A tone value outside the Tone enum returns 422."""
    resp = client.post("/agents", json=_create_payload(tone="grumpy"))
    assert resp.status_code == 422


def test_post_agents_full_payload_round_trips_through_get(client):
    """A fully-populated POST is recoverable verbatim via GET /agents/{id}."""
    payload = _create_payload(
        role="QA",
        description="Quality",
        tone="friendly",
        traits={"persona": "curious"},
        model={
            "provider": "gemini",
            "name": "gemini-3.1-flash-lite-preview",
            "temperature": 0.2,
            "max_output_tokens": 512,
        },
        limits={"max_run_tokens": 4000, "max_run_steps": 5, "daily_cost_usd": 1.0},
    )
    created = client.post("/agents", json=payload)
    assert created.status_code == 201
    agent_id = created.json()["id"]

    fetched = client.get(f"/agents/{agent_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["role"] == "QA"
    assert body["tone"] == "friendly"
    assert body["model"]["temperature"] == 0.2
    assert body["model"]["max_output_tokens"] == 512
    assert body["limits"]["max_run_tokens"] == 4000


# ---------- GET /agents (list) ----------


def test_get_agents_returns_items_and_total(client):
    """GET /agents returns the AgentList { items, total } shape."""
    client.post("/agents", json=_create_payload(name="A"))
    client.post("/agents", json=_create_payload(name="B"))

    resp = client.get("/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_get_agents_pagination(client):
    """?limit and ?offset paginate; total reflects the full row count."""
    for i in range(5):
        client.post("/agents", json=_create_payload(name=f"Agent {i}"))

    resp = client.get("/agents", params={"limit": 2, "offset": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


# ---------- GET /agents/{id} ----------


def test_get_agent_unknown_id_returns_404(client):
    """GET on an unknown id returns 404."""
    resp = client.get(f"/agents/{uuid4()}")
    assert resp.status_code == 404


# ---------- PUT /agents/{id} ----------


def test_put_agents_partial_update_only_changes_listed_fields(client):
    """A partial PUT body only changes the fields it lists; others are unchanged."""
    created = client.post("/agents", json=_create_payload(name="Original", role="QA"))
    agent_id = created.json()["id"]

    resp = client.put(f"/agents/{agent_id}", json={"name": "Renamed"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed"
    assert body["role"] == "QA"


def test_put_agents_updates_updated_at_not_created_at(client):
    """PUT bumps updated_at but leaves created_at alone."""
    created = client.post("/agents", json=_create_payload())
    agent_id = created.json()["id"]
    original_created = created.json()["created_at"]
    original_updated = created.json()["updated_at"]

    resp = client.put(f"/agents/{agent_id}", json={"name": "New"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_at"] == original_created
    assert body["updated_at"] != original_updated


def test_put_agents_unknown_id_returns_404(client):
    """PUT on an unknown id returns 404."""
    resp = client.put(f"/agents/{uuid4()}", json={"name": "x"})
    assert resp.status_code == 404


def test_put_agents_partial_nested_model_returns_422(client):
    """A partial nested model block (missing required fields) returns 422 —
    nested blocks must be whole-replace."""
    created = client.post("/agents", json=_create_payload())
    agent_id = created.json()["id"]

    resp = client.put(f"/agents/{agent_id}", json={"model": {"temperature": 0.5}})
    assert resp.status_code == 422


def test_put_agents_full_nested_model_block_returns_200(client):
    """A full nested model block replaces the existing ModelConfig wholesale."""
    created = client.post("/agents", json=_create_payload())
    agent_id = created.json()["id"]

    resp = client.put(
        f"/agents/{agent_id}",
        json={
            "model": {
                "provider": "anthropic",
                "name": "claude-3-5",
                "temperature": 0.7,
            }
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"]["provider"] == "anthropic"
    assert body["model"]["name"] == "claude-3-5"


# ---------- PUT /agents/{id} — lock-on-active-runs ----------


def test_put_agents_with_active_run_no_force_returns_409(client, monkeypatch):
    """Active runs + no ?force returns 409 with the blocking runs in the body."""
    created = client.post("/agents", json=_create_payload())
    agent_id = created.json()["id"]

    fake_run = RunRef(
        id=uuid4(), status=ActiveStatus.active, started_at=datetime.now(UTC)
    )
    monkeypatch.setattr(
        runs_service,
        "list_active_runs_for_agent",
        lambda session, agent_id: [fake_run],
    )

    resp = client.put(f"/agents/{agent_id}", json={"name": "New"})
    assert resp.status_code == 409
    body = resp.json()
    detail = body.get("detail", body)
    assert "active_runs" in detail
    assert detail["total"] == 1


def test_put_agents_force_true_query_succeeds_with_active_run(client, monkeypatch):
    """?force=true bypasses the lock and the PUT succeeds with 200."""
    created = client.post("/agents", json=_create_payload())
    agent_id = created.json()["id"]

    fake_run = RunRef(id=uuid4(), status=ActiveStatus.active)
    monkeypatch.setattr(
        runs_service,
        "list_active_runs_for_agent",
        lambda session, agent_id: [fake_run],
    )

    resp = client.put(
        f"/agents/{agent_id}",
        params={"force": "true"},
        json={"name": "Forced"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Forced"


def test_put_agents_with_pending_run_no_force_returns_409(client, monkeypatch):
    """Pending (not yet active) runs also block PUT without ?force."""
    created = client.post("/agents", json=_create_payload())
    agent_id = created.json()["id"]

    fake_run = RunRef(id=uuid4(), status=ActiveStatus.pending)
    monkeypatch.setattr(
        runs_service,
        "list_active_runs_for_agent",
        lambda session, agent_id: [fake_run],
    )

    resp = client.put(f"/agents/{agent_id}", json={"name": "New"})
    assert resp.status_code == 409
