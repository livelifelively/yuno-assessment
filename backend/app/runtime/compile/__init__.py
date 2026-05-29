"""Compile module — runtime-boundary adapter (yuno.Agent → crewai.Agent).

Per ADR-008 / ADR-009: pure projection function. No DB, no event-bus, no I/O.
Called once per run by the wrapper. See:
- spec:        yuno/3-how/specs/03-architecture/batches/1-single-agent-chat/modules/3-compile.md
- traceability: yuno/3-how/specs/03-architecture/traceability/compile.md

Batch 1 reads 3 of the 4 Batch-1 dimensions (Identity / Personality / Model);
Limits is yuno-enforced and stays on the agent for the wrapper to read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import crewai

from app.runtime.compile.errors import CompileError

if TYPE_CHECKING:
    from app.agents.domain import Agent, Tone


__all__ = ["CompileError", "compile_agent"]


# Batch-1 fixed default for crewai.Agent's required `goal` field. The yuno spec
# does not surface "goal" as an agent dimension in Batch 1; this placeholder
# satisfies CrewAI's constructor without introducing a spec-extending field.
# Becomes spec-driven if/when "goal" is added to the agent schema.
_DEFAULT_GOAL = "Respond to user requests as defined in your backstory."


def _build_role(name: str, role: str | None) -> str:
    """Identity → CrewAI `role` string per ADR-008.

    Combines name and role: `"{name}: {role}"` when both present;
    `name` alone when role is null.
    """
    if role:
        return f"{name}: {role}"
    return name


def _build_backstory(
    system_prompt: str,
    tone: Tone | None,
    traits: dict[str, Any] | None,
) -> str:
    """Personality → CrewAI `backstory` string per ADR-008.

    Starts with `system_prompt`. Appends a "Tone: {value}" line when tone is
    set. Appends each trait as a "{key}: {value}" line when traits are set.
    Lines are newline-separated.
    """
    parts: list[str] = [system_prompt]
    if tone is not None:
        parts.append(f"Tone: {tone.value}")
    if traits:
        for key, value in traits.items():
            parts.append(f"{key}: {value}")
    return "\n".join(parts)


def compile_agent(agent: Agent) -> crewai.Agent:
    """Project domain.Agent's Identity / Personality / Model dimensions into a
    configured crewai.Agent.

    Raises CompileError(field, reason) if a required field is missing or
    unusable. No CrewAI objects are constructed when validation fails —
    the wrapper catches CompileError and emits run.failed(compile_failed).
    """
    # B1.OC.6: short-circuit validation before any CrewAI construction.
    if not agent.system_prompt:
        raise CompileError(field="system_prompt", reason="required")
    if agent.model.provider is None:
        raise CompileError(field="model.provider", reason="required")
    if not agent.model.name:
        raise CompileError(field="model.name", reason="required")

    # Identity → role
    role = _build_role(agent.name, agent.role)

    # Personality → backstory
    backstory = _build_backstory(agent.system_prompt, agent.tone, agent.traits)

    # Model → llm. is_litellm=True forces CrewAI's LiteLLM dispatch path,
    # bypassing per-provider native wrappers (which rename / drop the
    # max_tokens kwarg). This is what makes yuno's `max_output_tokens` map
    # uniformly to LiteLLM's `max_tokens` across providers, per the ADR-008
    # mapping table.
    llm_kwargs: dict[str, Any] = {
        "model": f"{agent.model.provider}/{agent.model.name}",
        "is_litellm": True,
    }
    if agent.model.temperature is not None:
        llm_kwargs["temperature"] = agent.model.temperature
    if agent.model.max_output_tokens is not None:
        llm_kwargs["max_tokens"] = agent.model.max_output_tokens
    llm = crewai.LLM(**llm_kwargs)

    # Construct crewai.Agent with Batch-1 defaults pinned per
    # 3-compile.md's "CrewAI fields fixed at Batch-1 defaults" table.
    # max_iter is left at CrewAI's default (~25) by not passing it.
    return crewai.Agent(
        role=role,
        goal=_DEFAULT_GOAL,
        backstory=backstory,
        llm=llm,
        tools=[],
        allow_delegation=False,
        memory=False,
        verbose=False,
    )
