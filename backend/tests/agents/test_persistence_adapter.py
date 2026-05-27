"""Persistence adapter tests — pure functions over data, no DB."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.agents.domain import Agent, AgentLimits, ModelConfig, Provider, Tone
from app.agents.persistence import adapter
from app.agents.persistence.row import AgentRow


def _make_agent(**overrides) -> Agent:
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        name="X",
        role="QA",
        description="d",
        system_prompt="p",
        tone=Tone.friendly,
        traits={"k": "v"},
        model=ModelConfig(
            provider=Provider.gemini,
            name="gemini-3.1-flash-lite-preview",
            temperature=0.4,
            max_output_tokens=256,
        ),
        limits=AgentLimits(max_run_tokens=1000, max_run_steps=4, daily_cost_usd=0.5),
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return Agent(**defaults)


def _make_row(**overrides) -> AgentRow:
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        name="x",
        role=None,
        description=None,
        system_prompt="p",
        tone=None,
        traits=None,
        model_provider="gemini",
        model_name="gemini-3.1-flash-lite-preview",
        temperature=None,
        model_max_output_tokens=None,
        limits=None,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return AgentRow(**defaults)


def test_domain_to_row_flattens_model_into_columns():
    agent = _make_agent()
    row = adapter.domain_to_row(agent)

    assert row.model_provider == Provider.gemini.value
    assert row.model_name == "gemini-3.1-flash-lite-preview"
    assert row.temperature == 0.4
    assert row.model_max_output_tokens == 256


def test_domain_to_row_serializes_limits_as_jsonb_dict():
    agent = _make_agent()
    row = adapter.domain_to_row(agent)

    assert isinstance(row.limits, dict)
    assert row.limits["max_run_tokens"] == 1000
    assert row.limits["daily_cost_usd"] == 0.5


def test_row_to_domain_re_nests_model_columns():
    row = _make_row(
        model_provider="gemini",
        model_name="gemini-3.1-flash-lite-preview",
        temperature=0.3,
        model_max_output_tokens=128,
    )
    agent = adapter.row_to_domain(row)

    assert agent.model.provider == Provider.gemini
    assert agent.model.name == "gemini-3.1-flash-lite-preview"
    assert agent.model.temperature == 0.3
    assert agent.model.max_output_tokens == 128


def test_row_to_domain_re_hydrates_limits_from_jsonb():
    row = _make_row(
        limits={"max_run_tokens": 2000, "max_run_steps": 5, "daily_cost_usd": 1.0},
    )
    agent = adapter.row_to_domain(row)

    assert isinstance(agent.limits, AgentLimits)
    assert agent.limits.max_run_tokens == 2000
    assert agent.limits.max_run_steps == 5
    assert agent.limits.daily_cost_usd == 1.0


def test_row_to_domain_tone_string_parses_into_enum():
    row = _make_row(tone="professional")
    agent = adapter.row_to_domain(row)
    assert agent.tone == Tone.professional


def test_round_trip_domain_row_domain_matches_field_for_field():
    original = _make_agent()
    row = adapter.domain_to_row(original)
    recovered = adapter.row_to_domain(row)

    assert recovered.id == original.id
    assert recovered.name == original.name
    assert recovered.role == original.role
    assert recovered.tone == original.tone
    assert recovered.traits == original.traits
    assert recovered.model.provider == original.model.provider
    assert recovered.model.name == original.model.name
    assert recovered.model.temperature == original.model.temperature
    assert recovered.model.max_output_tokens == original.model.max_output_tokens
    assert recovered.limits is not None and original.limits is not None
    assert recovered.limits.max_run_tokens == original.limits.max_run_tokens
    assert recovered.limits.max_run_steps == original.limits.max_run_steps
    assert recovered.limits.daily_cost_usd == original.limits.daily_cost_usd


def test_round_trip_handles_none_fields():
    original = _make_agent(
        role=None, description=None, tone=None, traits=None, limits=None
    )
    row = adapter.domain_to_row(original)
    recovered = adapter.row_to_domain(row)

    assert recovered.role is None
    assert recovered.description is None
    assert recovered.tone is None
    assert recovered.traits is None
    assert recovered.limits is None


def test_apply_domain_to_row_in_place_preserves_orm_identity():
    row = _make_row(name="old")
    original_identity = id(row)

    new_agent = _make_agent(id=row.id, name="renamed")
    adapter.apply_domain_to_row(row, new_agent)

    assert id(row) == original_identity  # same instance
    assert row.name == "renamed"
    assert row.model_provider == Provider.gemini.value
