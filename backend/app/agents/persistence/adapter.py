"""Persistence boundary adapter — translates AgentRow ↔ domain Agent.

Per ADR-009, pure functions over data. No DB calls.
"""

from __future__ import annotations

from app.agents.domain import Agent, AgentLimits, ModelConfig, Provider, Tone
from app.agents.persistence.row import AgentRow


def row_to_domain(row: AgentRow) -> Agent:
    """Re-nests flat row columns into the domain Agent shape; re-hydrates
    JSONB limits into AgentLimits; parses tone string into Tone enum."""
    return Agent(
        id=row.id,
        name=row.name,
        role=row.role,
        description=row.description,
        system_prompt=row.system_prompt,
        tone=Tone(row.tone) if row.tone is not None else None,
        traits=row.traits,
        model=ModelConfig(
            provider=Provider(row.model_provider),
            name=row.model_name,
            temperature=row.temperature,
            max_output_tokens=row.model_max_output_tokens,
        ),
        limits=AgentLimits(**row.limits) if row.limits is not None else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def domain_to_row(agent: Agent) -> AgentRow:
    """Flattens the domain Agent's ModelConfig into model_* columns and
    serializes AgentLimits into the JSONB column."""
    return AgentRow(
        id=agent.id,
        name=agent.name,
        role=agent.role,
        description=agent.description,
        system_prompt=agent.system_prompt,
        tone=agent.tone.value if agent.tone is not None else None,
        traits=agent.traits,
        model_provider=agent.model.provider.value,
        model_name=agent.model.name,
        temperature=agent.model.temperature,
        model_max_output_tokens=agent.model.max_output_tokens,
        limits=agent.limits.model_dump() if agent.limits is not None else None,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def apply_domain_to_row(row: AgentRow, agent: Agent) -> None:
    """In-place update of an existing row to match the domain object.
    Used by repository.update so the ORM identity of the row is preserved.

    Does not touch id (immutable primary key) or created_at (set on insert).
    """
    row.name = agent.name
    row.role = agent.role
    row.description = agent.description
    row.system_prompt = agent.system_prompt
    row.tone = agent.tone.value if agent.tone is not None else None
    row.traits = agent.traits
    row.model_provider = agent.model.provider.value
    row.model_name = agent.model.name
    row.temperature = agent.model.temperature
    row.model_max_output_tokens = agent.model.max_output_tokens
    row.limits = agent.limits.model_dump() if agent.limits is not None else None
    row.updated_at = agent.updated_at
