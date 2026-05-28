"""HTTP request/response shapes for the runs module.

Per ADR-009, these are boundary representations — translated to/from domain
Run / RunEvent by app/runs/http/adapter.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.runs.domain import AbortReason, CancelReason, RunStatus


class RunCreate(BaseModel):
    """Body of POST /runs."""

    agent_id: UUID
    input: str = Field(min_length=1)


class CancelRequest(BaseModel):
    """Body of POST /runs/{id}/cancel — optional."""

    note: str | None = None


class RunRead(BaseModel):
    """1:1 mirror of domain Run. Response shape for every read endpoint
    and for POST /runs / POST /runs/{id}/cancel."""

    id: UUID
    agent_id: UUID
    status: RunStatus
    input: str
    output: str | None
    error_code: str | None
    error_message: str | None
    abort_reason: AbortReason | None
    cancel_reason: CancelReason | None
    token_usage_prompt: int
    token_usage_completion: int
    cost_usd: float
    step_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RunEventRead(BaseModel):
    """1:1 mirror of domain RunEvent."""

    id: UUID
    run_id: UUID
    sequence_number: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class RunList(BaseModel):
    items: list[RunRead]
    total: int


class RunEventList(BaseModel):
    items: list[RunEventRead]


class RunAlreadyTerminalResponse(BaseModel):
    """Body of the 409 from POST /runs/{id}/cancel when already terminal."""

    status: RunStatus
