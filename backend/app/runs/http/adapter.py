"""HTTP boundary adapter — translates DTOs ↔ domain. STUB (TDD RED phase)."""

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

_TODO = "TODO: GREEN phase — runs HTTP adapter"


def create_to_domain(
    data: RunCreate, *, id: UUID, now: datetime
) -> Run:
    """Build domain Run from RunCreate with persistence-owned fields populated
    (id, created_at=now, status=pending, all counters at 0)."""
    raise NotImplementedError(_TODO)


def domain_to_read(run: Run) -> RunRead:
    raise NotImplementedError(_TODO)


def event_to_read(event: RunEvent) -> RunEventRead:
    raise NotImplementedError(_TODO)


def runs_to_list(items: list[Run], total: int) -> RunList:
    raise NotImplementedError(_TODO)


def events_to_list(items: list[RunEvent]) -> RunEventList:
    raise NotImplementedError(_TODO)


def terminal_to_response(status: RunStatus) -> RunAlreadyTerminalResponse:
    """Build the 409 body for cancel-on-terminal-run from the run's
    current status."""
    raise NotImplementedError(_TODO)
