"""Repository operations — domain in/out, DB-aware. STUB (TDD RED phase)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.runs.domain import Run, RunEvent, RunRef, RunStatus

_TODO = "TODO: GREEN phase — runs repository"


def get(session: Session, run_id: UUID) -> Run | None:
    raise NotImplementedError(_TODO)


def list_(
    session: Session,
    *,
    status: RunStatus | None = None,
    agent_id: UUID | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[Run], int]:
    raise NotImplementedError(_TODO)


def count(
    session: Session,
    *,
    status: RunStatus | None = None,
    agent_id: UUID | None = None,
) -> int:
    raise NotImplementedError(_TODO)


def list_active_for_agent(session: Session, agent_id: UUID) -> list[RunRef]:
    raise NotImplementedError(_TODO)


def insert(session: Session, run: Run) -> Run:
    raise NotImplementedError(_TODO)


def apply_partial(
    session: Session, run_id: UUID, patch: dict[str, Any]
) -> Run:
    """Apply a column-shaped patch dict to an existing row. Raises
    RunNotFound if missing."""
    raise NotImplementedError(_TODO)


def sum_cost_for_agent_last_n_hours(
    session: Session, agent_id: UUID, hours: int
) -> float:
    raise NotImplementedError(_TODO)


def insert_event(session: Session, event: RunEvent) -> RunEvent:
    raise NotImplementedError(_TODO)


def list_events(session: Session, run_id: UUID) -> list[RunEvent]:
    raise NotImplementedError(_TODO)


def next_sequence_number(session: Session, run_id: UUID) -> int:
    """MAX(sequence_number) + 1 FOR run_id, computed inside a transaction
    serialized by the (run_id, sequence_number) UNIQUE constraint."""
    raise NotImplementedError(_TODO)
