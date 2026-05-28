"""HTTP boundary adapter — translates DTOs ↔ domain.

Per ADR-009, pure functions over data. No DB calls, no I/O.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.runs.domain import Run, RunEvent, RunStatus
from app.runs.http.dtos import (
    RunAlreadyTerminalResponse,
    RunCreate,
    RunEventList,
    RunEventRead,
    RunList,
    RunRead,
)


def create_to_domain(data: RunCreate, *, id: UUID, now: datetime) -> Run:
    """Build a domain Run from a RunCreate request, assigning the
    persistence-owned fields (id, created_at, status=pending, zero counters,
    null terminal fields)."""
    return Run(
        id=id,
        agent_id=data.agent_id,
        status=RunStatus.pending,
        input=data.input,
        output=None,
        error_code=None,
        error_message=None,
        abort_reason=None,
        cancel_reason=None,
        token_usage_prompt=0,
        token_usage_completion=0,
        cost_usd=0.0,
        step_count=0,
        created_at=now,
        started_at=None,
        completed_at=None,
    )


def domain_to_read(run: Run) -> RunRead:
    """1:1 mirror projection — every domain Run field surfaces on RunRead;
    nested AbortReason / CancelReason serialize as nested objects."""
    return RunRead.model_validate(run.model_dump())


def event_to_read(event: RunEvent) -> RunEventRead:
    """1:1 mirror of RunEvent including verbatim payload dict."""
    return RunEventRead.model_validate(event.model_dump())


def runs_to_list(items: list[Run], total: int) -> RunList:
    return RunList(items=[domain_to_read(r) for r in items], total=total)


def events_to_list(items: list[RunEvent]) -> RunEventList:
    return RunEventList(items=[event_to_read(e) for e in items])


def terminal_to_response(status: RunStatus) -> RunAlreadyTerminalResponse:
    return RunAlreadyTerminalResponse(status=status)
