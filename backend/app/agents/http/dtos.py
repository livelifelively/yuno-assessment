"""HTTP request/response shapes for the agents module.

Per ADR-009, these are boundary representations — translated to/from the
domain Agent by app/agents/http/adapter.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.agents.domain import Provider, Tone
from app.runs.domain import RunRef


class ModelConfigDTO(BaseModel):
    provider: Provider
    name: str
    temperature: float | None = None
    max_output_tokens: int | None = None

    model_config = ConfigDict(protected_namespaces=())


class AgentLimitsDTO(BaseModel):
    max_run_tokens: int | None = None
    max_run_steps: int | None = None
    daily_cost_usd: float | None = None


class AgentCreate(BaseModel):
    name: str
    role: str | None = None
    description: str | None = None
    system_prompt: str
    tone: Tone | None = None
    traits: dict[str, Any] | None = None
    model: ModelConfigDTO
    limits: AgentLimitsDTO | None = None

    model_config = ConfigDict(protected_namespaces=())


class AgentUpdate(BaseModel):
    """PATCH-style partial update. Identity comes from the URL path; `force`
    comes from the query string. Every field here is optional — present fields
    overwrite the column, absent fields leave it untouched. Nested model and
    limits are whole-replace when present."""

    name: str | None = None
    role: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    tone: Tone | None = None
    traits: dict[str, Any] | None = None
    model: ModelConfigDTO | None = None
    limits: AgentLimitsDTO | None = None

    model_config = ConfigDict(protected_namespaces=())


class AgentRead(BaseModel):
    id: UUID
    name: str
    role: str | None
    description: str | None
    system_prompt: str
    tone: Tone | None
    traits: dict[str, Any] | None
    model: ModelConfigDTO
    limits: AgentLimitsDTO | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(protected_namespaces=())


class AgentList(BaseModel):
    items: list[AgentRead]
    total: int


class AgentEditBlocked(BaseModel):
    """Body of the 409 response when PUT /agents/{id} hits active runs."""

    active_runs: list[RunRef]
    total: int
