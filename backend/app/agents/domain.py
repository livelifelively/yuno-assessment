"""Canonical domain shape for the agents module.

Per ADR-009, this is what service code consumes — HTTP DTOs and the AgentRow
persistence shape are boundary representations translated by adapters.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Tone(StrEnum):
    friendly = "friendly"
    professional = "professional"
    casual = "casual"
    formal = "formal"
    concise = "concise"
    playful = "playful"


class Provider(StrEnum):
    gemini = "gemini"
    anthropic = "anthropic"
    openai = "openai"


class ModelConfig(BaseModel):
    provider: Provider
    name: str
    temperature: float | None = None
    max_output_tokens: int | None = None

    model_config = ConfigDict(protected_namespaces=())


class AgentLimits(BaseModel):
    max_run_tokens: int | None = None
    max_run_steps: int | None = None
    daily_cost_usd: float | None = None


class Agent(BaseModel):
    """Canonical domain shape. The thing the service, the compile step, and
    (later) the export adapter operate on. id/created_at/updated_at are
    populated by persistence on insert/update."""

    id: UUID
    name: str
    role: str | None = None
    description: str | None = None
    system_prompt: str
    tone: Tone | None = None
    traits: dict[str, Any] | None = None
    model: ModelConfig
    limits: AgentLimits | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(protected_namespaces=())
