"""HTTP boundary adapter — translates DTOs ↔ domain Agent.

Per ADR-009, pure functions over data. No DB, no I/O.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.agents.domain import Agent, AgentLimits, ModelConfig
from app.agents.http.dtos import AgentCreate, AgentRead, AgentUpdate


def create_to_domain(data: AgentCreate, *, id: UUID, now: datetime) -> Agent:
    """Builds a domain Agent from an AgentCreate request, assigning the
    persistence-owned fields (id, created_at, updated_at)."""
    return Agent(
        id=id,
        name=data.name,
        role=data.role,
        description=data.description,
        system_prompt=data.system_prompt,
        tone=data.tone,
        traits=data.traits,
        model=ModelConfig(**data.model.model_dump()),
        limits=AgentLimits(**data.limits.model_dump()) if data.limits is not None else None,
        created_at=now,
        updated_at=now,
    )


def apply_update(existing: Agent, patch: AgentUpdate, *, now: datetime) -> Agent:
    """Merges a partial AgentUpdate into an existing domain Agent.

    Top-level absent fields leave the existing value untouched.
    Nested model/limits blocks are whole-replace when present, untouched when
    absent.
    """
    patch_set = patch.model_dump(exclude_unset=True)
    update_fields: dict = {}

    for field in ("name", "role", "description", "system_prompt", "tone", "traits"):
        if field in patch_set:
            update_fields[field] = getattr(patch, field)

    if "model" in patch_set and patch.model is not None:
        update_fields["model"] = ModelConfig(**patch.model.model_dump())

    if "limits" in patch_set:
        if patch.limits is None:
            update_fields["limits"] = None
        else:
            update_fields["limits"] = AgentLimits(**patch.limits.model_dump())

    update_fields["updated_at"] = now

    return existing.model_copy(update=update_fields)


def domain_to_read(agent: Agent) -> AgentRead:
    """Projects a domain Agent into the AgentRead response shape."""
    return AgentRead.model_validate(agent.model_dump())
