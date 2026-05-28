"""Persistence boundary adapter — translates rows ↔ domain. STUB (TDD RED phase)."""

from __future__ import annotations

from app.runs.domain import Run, RunEvent
from app.runs.persistence.row import RunEventRow, RunRow

_TODO = "TODO: GREEN phase — runs persistence adapter"


def row_to_domain(row: RunRow) -> Run:
    """Re-nest JSONB abort_reason / cancel_reason; parse status string to RunStatus."""
    raise NotImplementedError(_TODO)


def domain_to_row(run: Run) -> RunRow:
    """Flatten AbortReason / CancelReason into JSONB dicts; serialize status enum."""
    raise NotImplementedError(_TODO)


def apply_domain_to_row(row: RunRow, run: Run) -> None:
    """In-place update of an existing row to match the domain object.
    Preserves ORM identity. Does not touch id or created_at."""
    raise NotImplementedError(_TODO)


def event_row_to_domain(row: RunEventRow) -> RunEvent:
    raise NotImplementedError(_TODO)


def domain_to_event_row(event: RunEvent) -> RunEventRow:
    raise NotImplementedError(_TODO)
