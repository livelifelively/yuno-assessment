"""Service layer for the runs module — STUB (TDD RED phase).

Per ADR-009, functions take and return domain types only — never DTOs, never
rows, never raw bus payloads. The HTTP router and event-bus subscriber are
the two entry-point boundaries that translate before calling these.

`list_active_runs_for_agent` retains its Batch-1 stub behavior (returns []
for any agent_id) so the agents-module tests that depend on the empty-list
path stay green. Every other function raises NotImplementedError until the
GREEN phase wires the implementation through the repository.
"""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from app.runs.domain import Run, RunEvent, RunRef, RunStatus
from app.runtime.payloads import TokenUsage

_TODO = "TODO: GREEN phase — runs service implementation"


def create_run(session: Session, run: Run) -> Run:
    """Validate agent_id, insert with status=pending, spawn the wrapper task.

    Raises AgentNotFoundForRun if run.agent_id is not in agents.
    """
    raise NotImplementedError(_TODO)


def cancel_run(session: Session, run_id: UUID, note: str | None = None) -> Run:
    """Read the run, raise if missing or already terminal, publish run.cancelled.

    Returns the row at its current state — the subscriber transitions async.

    Raises RunNotFound, RunAlreadyTerminal(status).
    """
    raise NotImplementedError(_TODO)


def get_run(session: Session, run_id: UUID) -> Run | None:
    """Pure read. Returns None for missing — does not raise."""
    raise NotImplementedError(_TODO)


def list_runs(
    session: Session,
    *,
    status: RunStatus | None = None,
    agent_id: UUID | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[Run], int]:
    """Filtered + paginated list. limit defaults to settings.runs_default_list_limit
    and is clamped at settings.runs_max_list_limit. Total ignores pagination."""
    raise NotImplementedError(_TODO)


def list_active_runs_for_agent(session: Session, agent_id: UUID) -> list[RunRef]:
    """Returns runs in pending/active status for an agent.

    Kept as a Batch-1 stub returning [] so the agents-module tests that
    depend on the no-active-runs path stay green during the runs RED phase.
    GREEN phase replaces this body with a repository call.
    """
    return []


def get_run_events(session: Session, run_id: UUID) -> list[RunEvent]:
    """Returns events ordered by sequence_number ascending.

    Raises RunNotFound if the run is missing.
    """
    raise NotImplementedError(_TODO)


def get_daily_cost_for_agent(
    session: Session, agent_id: UUID, hours: int = 24
) -> float:
    """Sums cost_usd of runs with completed_at within the window."""
    raise NotImplementedError(_TODO)


# --- Helpers called by the event-bus subscriber ---


def transition_run_state(
    session: Session,
    run_id: UUID,
    target: RunStatus,
    **terminal_data,
) -> Run:
    """Validate the transition; apply via the repository. Raises
    InvalidRunTransition if the move is illegal per the state-machine table."""
    raise NotImplementedError(_TODO)


def accumulate_run_usage(
    session: Session, run_id: UUID, usage: TokenUsage, model: str
) -> Run:
    """Increment token_usage_* and add priced cost_usd via pricing.price_for.
    Logs a WARNING when the (provider, model) is not in PRICE_TABLE; cost
    accumulates 0.0 for the unpriced call but token counts still update."""
    raise NotImplementedError(_TODO)


def bump_step_count(session: Session, run_id: UUID) -> Run:
    """Increment step_count by 1. Called from the llm.call.started handler."""
    raise NotImplementedError(_TODO)


def append_run_event(session: Session, run_id: UUID, event) -> RunEvent:
    """Compute next sequence_number atomically; insert the RunEvent row.
    Stores event.payload verbatim — no filtering or re-projection."""
    raise NotImplementedError(_TODO)
