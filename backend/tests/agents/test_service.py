"""Service-layer tests for the agents module.

Direct calls to app.agents.service; bypasses the HTTP boundary. The runs lock
dependency is monkeypatched at app.runs.service.list_active_runs_for_agent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agents import service
from app.agents.domain import Agent, AgentLimits, ModelConfig, Provider, Tone
from app.agents.errors import AgentEditConflict, AgentNotFound
from app.runs import service as runs_service
from app.runs.domain import ActiveStatus, RunRef


def _make_agent(**overrides) -> Agent:
    """Build a domain Agent with sensible defaults; overrides set just the
    fields a test cares about."""
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        name="Test Agent",
        role=None,
        description=None,
        system_prompt="You are helpful.",
        tone=None,
        traits=None,
        model=ModelConfig(
            provider=Provider.gemini,
            name="gemini-3.1-flash-lite-preview",
        ),
        limits=None,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return Agent(**defaults)


def test_create_agent_persists_all_four_dimensions(db_session):
    """All four Batch 1 dimensions (Identity, Personality, Model, Limits)
    round-trip through create + get."""
    agent = _make_agent(
        role="QA",
        description="Quality assurance",
        tone=Tone.friendly,
        traits={"persona": "curious"},
        model=ModelConfig(
            provider=Provider.gemini,
            name="gemini-3.1-flash-lite-preview",
            temperature=0.2,
            max_output_tokens=512,
        ),
        limits=AgentLimits(max_run_tokens=4000, max_run_steps=5, daily_cost_usd=1.0),
    )
    result = service.create_agent(db_session, agent)
    assert result.id == agent.id

    fetched = service.get_agent(db_session, agent.id)
    assert fetched is not None
    assert fetched.name == "Test Agent"
    assert fetched.role == "QA"
    assert fetched.tone == Tone.friendly
    assert fetched.traits == {"persona": "curious"}
    assert fetched.model.temperature == 0.2
    assert fetched.model.max_output_tokens == 512
    assert fetched.limits is not None
    assert fetched.limits.max_run_tokens == 4000
    assert fetched.limits.daily_cost_usd == 1.0


def test_get_agent_returns_none_for_missing(db_session):
    """get_agent returns None for an unknown id; does not raise."""
    assert service.get_agent(db_session, uuid4()) is None


def test_update_agent_partial_leaves_untouched_fields(db_session):
    """Updating one field does not clobber the others."""
    original = _make_agent(name="Original", role="QA")
    service.create_agent(db_session, original)

    patched = original.model_copy(update={"name": "Renamed"})
    service.update_agent(db_session, patched, force=False)

    fetched = service.get_agent(db_session, original.id)
    assert fetched is not None
    assert fetched.name == "Renamed"
    assert fetched.role == "QA"


def test_update_agent_raises_not_found_for_missing(db_session):
    """update_agent raises AgentNotFound when the agent doesn't exist."""
    agent = _make_agent()  # never persisted
    with pytest.raises(AgentNotFound):
        service.update_agent(db_session, agent, force=False)


def test_update_agent_raises_conflict_when_active_runs_and_not_forced(
    db_session, monkeypatch
):
    """Lock check fires: with active runs and force=False, update_agent raises
    AgentEditConflict carrying the blocking runs."""
    agent = _make_agent()
    service.create_agent(db_session, agent)

    fake_run = RunRef(
        id=uuid4(), status=ActiveStatus.active, started_at=datetime.now(UTC)
    )
    monkeypatch.setattr(
        runs_service,
        "list_active_runs_for_agent",
        lambda session, agent_id: [fake_run],
    )

    with pytest.raises(AgentEditConflict) as exc_info:
        service.update_agent(db_session, agent, force=False)
    assert len(exc_info.value.active_runs) == 1
    assert exc_info.value.active_runs[0].id == fake_run.id


def test_update_agent_succeeds_when_forced_despite_active_runs(
    db_session, monkeypatch
):
    """force=True bypasses the lock; the in-flight run is not cancelled."""
    agent = _make_agent()
    service.create_agent(db_session, agent)

    fake_run = RunRef(id=uuid4(), status=ActiveStatus.active)
    monkeypatch.setattr(
        runs_service,
        "list_active_runs_for_agent",
        lambda session, agent_id: [fake_run],
    )

    patched = agent.model_copy(update={"name": "Forced rename"})
    service.update_agent(db_session, patched, force=True)

    fetched = service.get_agent(db_session, agent.id)
    assert fetched is not None
    assert fetched.name == "Forced rename"


def test_list_agents_pagination_and_total(db_session):
    """list_agents honors limit/offset; total reflects the full row count."""
    for i in range(5):
        service.create_agent(db_session, _make_agent(name=f"Agent {i}"))

    page, total = service.list_agents(db_session, limit=2, offset=1)
    assert total == 5
    assert len(page) == 2
