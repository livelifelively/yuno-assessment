"""Service layer for the runs module.

Per ADR-009, functions take and return domain types only — never DTOs, never
rows, never raw bus payloads. The HTTP router and event-bus subscriber are
the two entry-point boundaries that translate before calling these.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session

import app.runtime.wrapper.service as wrapper_service
from app.agents import service as agents_service
from app.event_bus import Event, bus as global_bus
from app.runs.domain import (
    AbortReason,
    CancelInitiator,
    CancelReason,
    Run,
    RunEvent,
    RunRef,
    RunStatus,
    TERMINAL_STATUSES,
)
from app.runs.errors import (
    AgentNotFoundForRun,
    InvalidRunTransition,
    RunAlreadyTerminal,
    RunNotFound,
)
from app.runs.event_bus.publisher import publish_run_cancelled
from app.runs.persistence import repository
from app.runs.pricing import price_for
from app.runtime.payloads import TokenUsage
from app.settings import settings


log = logging.getLogger(__name__)


# State-machine: legal transitions and the columns each one writes.
_LEGAL_TRANSITIONS: dict[tuple[RunStatus, RunStatus], frozenset[str]] = {
    (RunStatus.pending, RunStatus.active): frozenset({"started_at"}),
    (RunStatus.pending, RunStatus.failed): frozenset(
        {"error_code", "error_message", "completed_at"}
    ),
    (RunStatus.pending, RunStatus.cancelled): frozenset(
        {"cancel_reason", "completed_at"}
    ),
    (RunStatus.active, RunStatus.completed): frozenset({"output", "completed_at"}),
    (RunStatus.active, RunStatus.failed): frozenset(
        {"error_code", "error_message", "completed_at"}
    ),
    (RunStatus.active, RunStatus.aborted): frozenset(
        {"abort_reason", "completed_at"}
    ),
    (RunStatus.active, RunStatus.cancelled): frozenset(
        {"cancel_reason", "completed_at"}
    ),
}


# --- HTTP-surface methods ---


def create_run(session: Session, run: Run) -> Run:
    """Validate agent_id, insert with status=pending, spawn the wrapper task.

    Raises AgentNotFoundForRun if run.agent_id is not in agents.
    """
    if agents_service.get_agent(session, run.agent_id) is None:
        raise AgentNotFoundForRun(f"Agent {run.agent_id} not found")

    persisted = repository.insert(session, run)
    _spawn_wrapper(persisted.id)
    return persisted


def cancel_run(session: Session, run_id: UUID, note: str | None = None) -> Run:
    """Publish run.cancelled and return the row at its current state — the
    subscriber transitions async. Raises RunNotFound / RunAlreadyTerminal."""
    current = repository.get(session, run_id)
    if current is None:
        raise RunNotFound(f"Run {run_id} not found")
    if current.status in TERMINAL_STATUSES:
        raise RunAlreadyTerminal(current.status)

    reason = CancelReason(
        initiated_by=CancelInitiator.operator,
        requested_at=datetime.now(UTC),
        note=note,
    )
    # Fire-and-forget publish to the in-process bus.
    _run_coroutine(publish_run_cancelled(global_bus, run_id, reason))
    return current


def get_run(session: Session, run_id: UUID) -> Run | None:
    """Pure read. Returns None for missing — does not raise."""
    return repository.get(session, run_id)


def list_runs(
    session: Session,
    *,
    status: RunStatus | None = None,
    agent_id: UUID | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[Run], int]:
    """Filtered + paginated list. `limit` defaults to
    `settings.runs_default_list_limit` and is clamped at
    `settings.runs_max_list_limit`."""
    effective_limit = limit if limit is not None else settings.runs_default_list_limit
    effective_limit = min(effective_limit, settings.runs_max_list_limit)
    return repository.list_(
        session,
        status=status,
        agent_id=agent_id,
        limit=effective_limit,
        offset=offset,
    )


def list_active_runs_for_agent(session: Session, agent_id: UUID) -> list[RunRef]:
    """Returns runs in pending/active status for an agent. Used by the
    agents-module lock check on PUT /agents/{id}."""
    return repository.list_active_for_agent(session, agent_id)


def get_run_events(session: Session, run_id: UUID) -> list[RunEvent]:
    """Returns events ordered by sequence_number ascending. Raises
    RunNotFound if the run is missing."""
    if repository.get(session, run_id) is None:
        raise RunNotFound(f"Run {run_id} not found")
    return repository.list_events(session, run_id)


def get_daily_cost_for_agent(
    session: Session, agent_id: UUID, hours: int = 24
) -> float:
    """Sums cost_usd of runs with completed_at within the window."""
    return repository.sum_cost_for_agent_last_n_hours(session, agent_id, hours)


# --- Helpers called by the event-bus subscriber ---


def transition_run_state(
    session: Session,
    run_id: UUID,
    target: RunStatus,
    *,
    output: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    abort_reason: AbortReason | None = None,
    cancel_reason: CancelReason | None = None,
    completed_at: datetime | None = None,
    started_at: datetime | None = None,
) -> Run:
    """Validate the transition; apply via the repository. Raises
    InvalidRunTransition if the move is illegal per the state-machine table."""
    current = repository.get(session, run_id)
    if current is None:
        raise RunNotFound(f"Run {run_id} not found")
    if (current.status, target) not in _LEGAL_TRANSITIONS:
        raise InvalidRunTransition(current.status, target)

    patch: dict = {"status": target.value}
    if started_at is not None:
        patch["started_at"] = started_at
    if completed_at is not None:
        patch["completed_at"] = completed_at
    if output is not None:
        patch["output"] = output
    if error_code is not None:
        patch["error_code"] = error_code
    if error_message is not None:
        patch["error_message"] = error_message
    if abort_reason is not None:
        patch["abort_reason"] = abort_reason.model_dump(mode="json")
    if cancel_reason is not None:
        patch["cancel_reason"] = cancel_reason.model_dump(mode="json")

    return repository.apply_partial(session, run_id, patch)


def accumulate_run_usage(
    session: Session, run_id: UUID, usage: TokenUsage, model: str
) -> Run:
    """Increment token_usage_* and add priced cost_usd via pricing.price_for.
    Logs a WARNING when the model is not in PRICE_TABLE; tokens still
    accumulate, cost stays unchanged for the unpriced call."""
    current = repository.get(session, run_id)
    if current is None:
        raise RunNotFound(f"Run {run_id} not found")

    new_prompt = current.token_usage_prompt + usage.prompt_tokens
    new_completion = current.token_usage_completion + usage.completion_tokens

    prices = price_for(model)
    if prices is None:
        log.warning(
            "no price configured for model=%s; cost_usd will undercount",
            model,
        )
        new_cost = current.cost_usd
    else:
        price_in, price_out = prices
        delta = (usage.prompt_tokens * price_in + usage.completion_tokens * price_out) / 1000
        new_cost = current.cost_usd + delta

    return repository.apply_partial(
        session,
        run_id,
        {
            "token_usage_prompt": new_prompt,
            "token_usage_completion": new_completion,
            "cost_usd": new_cost,
        },
    )


def bump_step_count(session: Session, run_id: UUID) -> Run:
    """Increment step_count by 1. Called from the llm.call.started handler."""
    current = repository.get(session, run_id)
    if current is None:
        raise RunNotFound(f"Run {run_id} not found")
    return repository.apply_partial(
        session, run_id, {"step_count": current.step_count + 1}
    )


def append_run_event(session: Session, run_id: UUID, event: Event) -> RunEvent:
    """Compute next sequence_number; insert the RunEvent row with the bus
    event's payload stored verbatim. The (run_id, sequence_number) UNIQUE
    constraint provides defence-in-depth against concurrent races."""
    seq = repository.next_sequence_number(session, run_id)
    domain_event = RunEvent(
        run_id=run_id,
        sequence_number=seq,
        event_type=event.type,
        payload=event.payload,
        occurred_at=event.occurred_at,
        id=event.id,
    )
    return repository.insert_event(session, domain_event)


# --- Private helpers ---


def _spawn_wrapper(run_id: UUID) -> None:
    """Schedule WrapperService.run_agent(run_id) without blocking the caller.

    In an async context (FastAPI's async route handler): grabs the running
    loop and schedules via `loop.create_task` — fire-and-forget.
    In a sync context with no running loop (tests, scripts): runs the
    coroutine synchronously via `asyncio.run` — the test waits on completion.
    """
    _run_coroutine(wrapper_service.run_agent(run_id))


def _run_coroutine(coro) -> None:
    """Schedule a coroutine without propagating its exceptions to the caller.

    Fire-and-forget: a background task that crashes is logged but never
    bubbles up. Crucial for the wrapper-spawn path — `run_agent` running
    forever (or raising) inside a request handler must not affect the 202
    response.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(coro)
        except Exception:
            log.exception("background task failed")
    else:
        loop.create_task(coro)
