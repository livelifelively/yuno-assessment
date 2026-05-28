"""Canonical domain shapes for the runs module.

Per ADR-009, service / repository / subscriber operate on these types. HTTP
DTOs (`app/runs/http/dtos.py`), persistence rows (`app/runs/persistence/row.py`),
and bus payloads (`app/runs/event_bus/payloads.py` plus the inbound payloads
imported from wrapper/runtime) are boundary representations translated by
adapters.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# --- Enums ---


class RunStatus(StrEnum):
    pending = "pending"
    active = "active"
    completed = "completed"
    failed = "failed"
    aborted = "aborted"
    cancelled = "cancelled"


class ActiveStatus(StrEnum):
    pending = "pending"
    active = "active"


class LimitName(StrEnum):
    max_run_tokens = "max_run_tokens"
    max_run_steps = "max_run_steps"
    daily_cost_usd = "daily_cost_usd"


class CancelInitiator(StrEnum):
    operator = "operator"


TERMINAL_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.completed, RunStatus.failed, RunStatus.aborted, RunStatus.cancelled}
)


# --- Value objects carried on Run ---


class AbortReason(BaseModel):
    """Carried on Run.abort_reason when status is aborted. System-initiated."""

    limit: LimitName
    value: float
    cap: float


class CancelReason(BaseModel):
    """Carried on Run.cancel_reason when status is cancelled. Operator-initiated."""

    initiated_by: CancelInitiator
    requested_at: datetime
    note: str | None = None


# --- Aggregate domain shapes ---


class Run(BaseModel):
    """Canonical Pydantic shape for one agent run."""

    id: UUID
    agent_id: UUID
    status: RunStatus
    input: str
    output: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    abort_reason: AbortReason | None = None
    cancel_reason: CancelReason | None = None
    token_usage_prompt: int = 0
    token_usage_completion: int = 0
    cost_usd: float = 0.0
    step_count: int = 0
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunEvent(BaseModel):
    """Canonical Pydantic shape for one event row — append-only audit log."""

    id: UUID
    run_id: UUID
    sequence_number: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class RunRef(BaseModel):
    """Slim cross-module reference to an in-flight run. Returned by
    list_active_runs_for_agent for the agents-module lock check."""

    id: UUID
    status: ActiveStatus
    started_at: datetime | None = None


# --- Helpers used across adapter / subscriber / service ---


def is_terminal(status: RunStatus) -> bool:
    return status in TERMINAL_STATUSES


__all__ = [
    "RunStatus",
    "ActiveStatus",
    "LimitName",
    "CancelInitiator",
    "TERMINAL_STATUSES",
    "AbortReason",
    "CancelReason",
    "Run",
    "RunEvent",
    "RunRef",
    "is_terminal",
    # Re-export for ergonomic Field default factory imports downstream
    "Field",
]
