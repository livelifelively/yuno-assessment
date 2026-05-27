"""HTTP adapter tests — pure functions over data, no DB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.agents.domain import Agent, AgentLimits, ModelConfig, Provider, Tone
from app.agents.http import adapter
from app.agents.http.dtos import (
    AgentCreate,
    AgentLimitsDTO,
    AgentUpdate,
    ModelConfigDTO,
)


def _make_create_dto() -> AgentCreate:
    """Build a fully-populated AgentCreate DTO for adapter input."""
    return AgentCreate(
        name="A",
        role="QA",
        description="Quality",
        system_prompt="Be helpful",
        tone=Tone.friendly,
        traits={"persona": "curious"},
        model=ModelConfigDTO(
            provider=Provider.gemini,
            name="gemini-3.1-flash-lite-preview",
            temperature=0.2,
            max_output_tokens=512,
        ),
        limits=AgentLimitsDTO(
            max_run_tokens=4000, max_run_steps=5, daily_cost_usd=1.0
        ),
    )


def _make_agent(**overrides) -> Agent:
    """Build a domain Agent with sensible defaults; overrides set just the
    fields a test cares about."""
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        name="Existing",
        role="QA",
        description="d",
        system_prompt="prompt",
        tone=Tone.friendly,
        traits={"k": "v"},
        model=ModelConfig(
            provider=Provider.gemini,
            name="gemini-3.1-flash-lite-preview",
            temperature=0.5,
            max_output_tokens=200,
        ),
        limits=AgentLimits(max_run_tokens=1000, max_run_steps=3, daily_cost_usd=0.5),
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return Agent(**defaults)


def test_create_to_domain_assigns_persistence_owned_fields():
    """create_to_domain populates id / created_at / updated_at from arguments."""
    create = _make_create_dto()
    agent_id = uuid4()
    now = datetime.now(UTC)

    agent = adapter.create_to_domain(create, id=agent_id, now=now)

    assert agent.id == agent_id
    assert agent.created_at == now
    assert agent.updated_at == now
    assert agent.name == "A"
    assert agent.tone == Tone.friendly
    assert agent.model.provider == Provider.gemini
    assert agent.limits is not None
    assert agent.limits.max_run_tokens == 4000


def test_apply_update_top_level_present_overwrites():
    """Top-level fields present in the patch overwrite the existing value."""
    existing = _make_agent(name="Existing", role="QA")
    patch = AgentUpdate(name="New")
    now = datetime.now(UTC)

    updated = adapter.apply_update(existing, patch, now=now)

    assert updated.name == "New"
    assert updated.role == existing.role
    assert updated.system_prompt == existing.system_prompt


def test_apply_update_top_level_absent_leaves_existing():
    """Top-level fields absent from the patch leave the existing value alone."""
    existing = _make_agent(name="Existing", role="QA", description="orig")
    patch = AgentUpdate(name="New")
    now = datetime.now(UTC)

    updated = adapter.apply_update(existing, patch, now=now)

    assert updated.role == "QA"
    assert updated.description == "orig"


def test_apply_update_nested_model_present_wholly_replaces():
    """A present nested model block replaces the existing ModelConfig wholesale."""
    existing = _make_agent(
        model=ModelConfig(
            provider=Provider.gemini, name="old-model", temperature=0.1
        ),
    )
    patch = AgentUpdate(
        model=ModelConfigDTO(
            provider=Provider.anthropic, name="claude-3-5", temperature=0.9
        ),
    )
    now = datetime.now(UTC)

    updated = adapter.apply_update(existing, patch, now=now)

    assert updated.model.provider == Provider.anthropic
    assert updated.model.name == "claude-3-5"
    assert updated.model.temperature == 0.9
    assert updated.model.max_output_tokens is None  # explicit absence in the new block


def test_apply_update_nested_model_absent_leaves_existing():
    """An absent model block leaves the existing ModelConfig untouched."""
    existing = _make_agent()
    patch = AgentUpdate(name="renamed")
    now = datetime.now(UTC)

    updated = adapter.apply_update(existing, patch, now=now)

    assert updated.model == existing.model


def test_apply_update_nested_limits_present_wholly_replaces():
    """A present nested limits block replaces the existing AgentLimits wholesale."""
    existing = _make_agent(limits=AgentLimits(max_run_tokens=1000))
    patch = AgentUpdate(
        limits=AgentLimitsDTO(
            max_run_tokens=2000, max_run_steps=10, daily_cost_usd=5.0
        ),
    )
    now = datetime.now(UTC)

    updated = adapter.apply_update(existing, patch, now=now)

    assert updated.limits is not None
    assert updated.limits.max_run_tokens == 2000
    assert updated.limits.max_run_steps == 10
    assert updated.limits.daily_cost_usd == 5.0


def test_apply_update_nested_limits_absent_leaves_existing():
    """An absent limits block leaves the existing AgentLimits untouched."""
    existing = _make_agent(limits=AgentLimits(max_run_tokens=1000))
    patch = AgentUpdate(name="x")
    now = datetime.now(UTC)

    updated = adapter.apply_update(existing, patch, now=now)

    assert updated.limits == existing.limits


def test_apply_update_sets_updated_at_not_created_at():
    """apply_update sets updated_at from the `now` argument; created_at is unchanged."""
    existing = _make_agent()
    original_created = existing.created_at
    later = original_created + timedelta(seconds=1)

    updated = adapter.apply_update(existing, AgentUpdate(name="x"), now=later)

    assert updated.created_at == original_created
    assert updated.updated_at == later


def test_domain_to_read_surfaces_all_fields():
    """domain_to_read projects every domain Agent field onto AgentRead."""
    agent = _make_agent()
    read = adapter.domain_to_read(agent)

    assert read.id == agent.id
    assert read.name == agent.name
    assert read.tone == agent.tone
    assert read.model.provider == agent.model.provider
    assert read.model.name == agent.model.name
    assert read.limits is not None and agent.limits is not None
    assert read.limits.max_run_tokens == agent.limits.max_run_tokens


def test_round_trip_create_to_read_matches_input_fields():
    """AgentCreate → create_to_domain → domain_to_read preserves every input field."""
    create = _make_create_dto()
    agent_id = uuid4()
    now = datetime.now(UTC)

    agent = adapter.create_to_domain(create, id=agent_id, now=now)
    read = adapter.domain_to_read(agent)

    assert read.name == create.name
    assert read.role == create.role
    assert read.description == create.description
    assert read.system_prompt == create.system_prompt
    assert read.tone == create.tone
    assert read.traits == create.traits
    assert read.model.provider == create.model.provider
    assert read.model.name == create.model.name
    assert read.model.temperature == create.model.temperature
    assert read.model.max_output_tokens == create.model.max_output_tokens
    assert read.limits is not None and create.limits is not None
    assert read.limits.max_run_tokens == create.limits.max_run_tokens
