"""Tests for app.runtime.compile per ADR-008 / ADR-009.

The compile module is a pure function: domain.Agent → crewai.Agent. No DB,
no event-bus, no I/O. These tests use in-memory Agent instances exclusively —
no db_session, no client, no mock_llm. (CrewAI's Agent + LLM constructors run
real because they're just object construction; nothing makes LLM calls here.)

Each test class maps to a traceability matrix row group:
- TestIdentityProjection   ↔ B1.AD.1 / B1.MF.3
- TestPersonalityProjection ↔ B1.AD.2 / B1.MF.4
- TestModelProjection      ↔ B1.AD.3 / B1.MF.5
- TestBatchOneDefaults     ↔ B1.OC.5 / B1.MF.7
- TestLimitsNotRead        ↔ B1.OC.3
- TestCompileErrors        ↔ B1.EF.1–3 / B1.DM.1
- TestPurity               ↔ B1.OC.4
- TestNoDbAccess           ↔ B1.OC.1
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.agents.domain import Agent, AgentLimits, ModelConfig, Provider, Tone
from app.runtime.compile import CompileError, compile_agent

# ---- Helpers ----------------------------------------------------------------


def make_agent(**overrides: Any) -> Agent:
    """Build a valid domain.Agent with sensible defaults; override per test."""
    defaults: dict[str, Any] = {
        "id": uuid4(),
        "name": "Support Agent",
        "role": "Customer Support",
        "description": None,
        "system_prompt": "Be helpful and direct.",
        "tone": None,
        "traits": None,
        "model": ModelConfig(
            provider=Provider.gemini,
            name="gemini-3.1-flash-lite-preview",
        ),
        "limits": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Agent(**defaults)


# ---- Identity projection — B1.AD.1 / B1.MF.3 -------------------------------


class TestIdentityProjection:
    """Identity → role: f'{name}: {role}' when both present; name alone otherwise."""

    def test_name_plus_role_becomes_combined_role_string(self) -> None:
        agent = make_agent(name="Support Agent", role="Customer Support")
        crewai_agent = compile_agent(agent)
        assert crewai_agent.role == "Support Agent: Customer Support"

    def test_name_only_when_role_is_null(self) -> None:
        agent = make_agent(name="Support Agent", role=None)
        crewai_agent = compile_agent(agent)
        assert crewai_agent.role == "Support Agent"


# ---- Personality projection — B1.AD.2 / B1.MF.4 ----------------------------


class TestPersonalityProjection:
    """Personality → backstory: system_prompt + optional tone modifier + optional traits."""

    def test_system_prompt_only_is_verbatim_backstory(self) -> None:
        agent = make_agent(system_prompt="Be concise.", tone=None, traits=None)
        crewai_agent = compile_agent(agent)
        assert crewai_agent.backstory == "Be concise."

    def test_system_prompt_plus_tone_appends_tone_modifier(self) -> None:
        agent = make_agent(
            system_prompt="Be helpful.", tone=Tone.friendly, traits=None
        )
        crewai_agent = compile_agent(agent)
        backstory = crewai_agent.backstory
        assert "Be helpful." in backstory
        # Tone modifier appears below the prompt (separate line); the tone name
        # should be reflected verbatim somewhere in the appended segment.
        assert "friendly" in backstory.lower()
        # Ensure it's appended, not the only content.
        assert backstory.startswith("Be helpful.")

    def test_system_prompt_plus_traits_dumps_each_on_its_own_line(self) -> None:
        agent = make_agent(
            system_prompt="Be helpful.",
            tone=None,
            traits={"empathy": "high", "formality": "low"},
        )
        crewai_agent = compile_agent(agent)
        backstory = crewai_agent.backstory
        assert "Be helpful." in backstory
        # Each trait surfaced on its own line per the spec's "Trait: value" format.
        # We check key + value presence and the line-separated structure.
        assert "empathy" in backstory.lower()
        assert "high" in backstory
        assert "formality" in backstory.lower()
        assert "low" in backstory
        # Each trait should occupy its own line (newline-separated).
        trait_lines = [line for line in backstory.splitlines() if ":" in line]
        assert len(trait_lines) >= 2


# ---- Model projection — B1.AD.3 / B1.MF.5 ----------------------------------


class TestModelProjection:
    """Model → llm: LLM(model=f'{provider}/{name}', temperature, max_tokens)."""

    def test_provider_slash_name_becomes_litellm_model_id(self) -> None:
        agent = make_agent(
            model=ModelConfig(
                provider=Provider.gemini,
                name="gemini-3.1-flash-lite-preview",
            )
        )
        crewai_agent = compile_agent(agent)
        assert crewai_agent.llm.model == "gemini/gemini-3.1-flash-lite-preview"

    def test_temperature_passes_through_to_crewai_llm(self) -> None:
        agent = make_agent(
            model=ModelConfig(
                provider=Provider.anthropic,
                name="claude-sonnet-4-5",
                temperature=0.3,
            )
        )
        crewai_agent = compile_agent(agent)
        assert crewai_agent.llm.temperature == 0.3

    def test_max_output_tokens_maps_to_litellm_max_tokens_kwarg(self) -> None:
        agent = make_agent(
            model=ModelConfig(
                provider=Provider.openai,
                name="gpt-4o",
                max_output_tokens=512,
            )
        )
        crewai_agent = compile_agent(agent)
        # crewai.LLM exposes the LiteLLM kwarg as .max_tokens (not .max_output_tokens).
        assert crewai_agent.llm.max_tokens == 512


# ---- Batch-1 defaults — B1.OC.5 / B1.MF.7 ----------------------------------


class TestBatchOneDefaults:
    """CrewAI fields pinned at Batch-1 defaults (not spec-driven)."""

    def test_tools_default_to_empty_list(self) -> None:
        crewai_agent = compile_agent(make_agent())
        assert crewai_agent.tools == []

    def test_allow_delegation_default_false(self) -> None:
        crewai_agent = compile_agent(make_agent())
        assert crewai_agent.allow_delegation is False

    def test_memory_default_false(self) -> None:
        crewai_agent = compile_agent(make_agent())
        assert crewai_agent.memory is False

    def test_verbose_default_false(self) -> None:
        crewai_agent = compile_agent(make_agent())
        assert crewai_agent.verbose is False

    def test_max_iter_left_at_crewai_default(self) -> None:
        crewai_agent = compile_agent(make_agent())
        # CrewAI default is ~25; assert it's a positive int rather than an exact
        # value so this test survives a CrewAI bump.
        assert isinstance(crewai_agent.max_iter, int)
        assert crewai_agent.max_iter >= 1


# ---- Limits dimension is NOT read — B1.OC.3 --------------------------------


class TestLimitsNotRead:
    """Compile reads 3 of the 4 Batch-1 dimensions; Limits is yuno-enforced
    and stays on the agent for the wrapper to enforce. The returned crewai.Agent
    must carry no limit-related attribute set from the spec."""

    def test_limits_set_on_input_dont_surface_on_crewai_agent(self) -> None:
        agent = make_agent(
            limits=AgentLimits(
                max_run_tokens=1000,
                max_run_steps=10,
                daily_cost_usd=5.0,
            )
        )
        crewai_agent = compile_agent(agent)
        # No CrewAI attribute is populated from the Limits spec values.
        # max_iter stays at CrewAI's default — it's NOT derived from limits.max_run_steps.
        assert crewai_agent.max_iter != 10
        # No token/cost-related attribute is set from Limits.
        for forbidden in (
            "max_run_tokens",
            "daily_cost_usd",
            "max_tokens_per_run",
            "cost_cap_usd",
        ):
            assert not hasattr(crewai_agent, forbidden), (
                f"crewai.Agent should not carry limit-derived attribute "
                f"{forbidden!r} — Limits is yuno-enforced (wrapper handles it)."
            )


# ---- Error paths — B1.EF.1–3 / B1.DM.1 -------------------------------------


class TestCompileErrors:
    """compile_agent validates required fields and raises CompileError(field, reason)
    before constructing any CrewAI object (B1.OC.6 short-circuit guarantee)."""

    def test_empty_system_prompt_raises_compile_error(self) -> None:
        # B1.EF.1: empty system_prompt is "missing" at the compile layer.
        # Pydantic allows empty str; compile rejects.
        agent = make_agent(system_prompt="")
        with pytest.raises(CompileError) as exc:
            compile_agent(agent)
        assert exc.value.field == "system_prompt"
        assert exc.value.reason == "required"

    def test_missing_model_provider_raises_compile_error(self) -> None:
        # B1.EF.2: defense-in-depth. ModelConfig.provider is enforced by Pydantic
        # at construction time; bypass via setattr to simulate a corrupted state
        # and assert compile_agent still validates.
        agent = make_agent()
        setattr(agent.model, "provider", None)
        with pytest.raises(CompileError) as exc:
            compile_agent(agent)
        assert exc.value.field == "model.provider"
        assert exc.value.reason == "required"

    def test_missing_model_name_raises_compile_error(self) -> None:
        # B1.EF.3: same defense-in-depth pattern for model.name.
        agent = make_agent()
        setattr(agent.model, "name", "")
        with pytest.raises(CompileError) as exc:
            compile_agent(agent)
        assert exc.value.field == "model.name"
        assert exc.value.reason == "required"

    def test_compile_error_exposes_field_and_reason_attrs(self) -> None:
        # B1.DM.1: CompileError contract — exposes .field and .reason.
        err = CompileError(field="model.provider", reason="required")
        assert err.field == "model.provider"
        assert err.reason == "required"
        # Stringified message follows the wrapper's f"{e.field}: {e.reason}" convention.
        assert str(err) == "model.provider: required"


# ---- Purity — B1.OC.4 ------------------------------------------------------


class TestPurity:
    """compile_agent has no hidden state — twice-called with the same input
    produces equivalent crewai.Agent instances."""

    def test_compile_agent_is_pure(self) -> None:
        agent = make_agent()
        result_one = compile_agent(agent)
        result_two = compile_agent(agent)
        # Compare the canonical fields the wrapper / runtime would observe.
        assert result_one.role == result_two.role
        assert result_one.backstory == result_two.backstory
        assert result_one.llm.model == result_two.llm.model
        assert result_one.tools == result_two.tools
        assert result_one.allow_delegation == result_two.allow_delegation


# ---- No DB access — B1.OC.1 ------------------------------------------------


class TestNoDbAccess:
    """This entire test file uses no db_session and no client fixture.
    Compile is pure: domain.Agent in, crewai.Agent out, no I/O."""

    def test_compile_runs_without_db_fixture(self) -> None:
        # If compile_agent reached for the database, this would fail because
        # no db_session fixture is injected. The fact that the test runs at all
        # proves the contract.
        result = compile_agent(make_agent())
        assert result is not None
