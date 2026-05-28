"""Persistence boundary adapter — translates rows ↔ domain.

Per ADR-009, pure functions over data. No DB calls.
"""

from __future__ import annotations

from app.runs.domain import (
    AbortReason,
    CancelReason,
    Run,
    RunEvent,
    RunStatus,
)
from app.runs.persistence.row import RunEventRow, RunRow


def row_to_domain(row: RunRow) -> Run:
    """Parse the row's status string into RunStatus; re-hydrate JSONB
    abort_reason / cancel_reason into their value objects."""
    return Run(
        id=row.id,
        agent_id=row.agent_id,
        status=RunStatus(row.status),
        input=row.input,
        output=row.output,
        error_code=row.error_code,
        error_message=row.error_message,
        abort_reason=(
            AbortReason(**row.abort_reason) if row.abort_reason is not None else None
        ),
        cancel_reason=(
            CancelReason(**row.cancel_reason) if row.cancel_reason is not None else None
        ),
        token_usage_prompt=row.token_usage_prompt,
        token_usage_completion=row.token_usage_completion,
        cost_usd=row.cost_usd,
        step_count=row.step_count,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def domain_to_row(run: Run) -> RunRow:
    """Serialize the RunStatus enum as its string value; dump AbortReason /
    CancelReason into dicts bound for the JSONB columns."""
    return RunRow(
        id=run.id,
        agent_id=run.agent_id,
        status=run.status.value,
        input=run.input,
        output=run.output,
        error_code=run.error_code,
        error_message=run.error_message,
        abort_reason=(
            run.abort_reason.model_dump(mode="json")
            if run.abort_reason is not None
            else None
        ),
        cancel_reason=(
            run.cancel_reason.model_dump(mode="json")
            if run.cancel_reason is not None
            else None
        ),
        token_usage_prompt=run.token_usage_prompt,
        token_usage_completion=run.token_usage_completion,
        cost_usd=run.cost_usd,
        step_count=run.step_count,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def apply_domain_to_row(row: RunRow, run: Run) -> None:
    """In-place update of an existing row to match the domain object.

    Preserves ORM identity (mutates the existing instance rather than
    constructing a new one). Does not touch `id` (immutable PK) or
    `created_at` (set on insert).
    """
    row.agent_id = run.agent_id
    row.status = run.status.value
    row.input = run.input
    row.output = run.output
    row.error_code = run.error_code
    row.error_message = run.error_message
    row.abort_reason = (
        run.abort_reason.model_dump(mode="json")
        if run.abort_reason is not None
        else None
    )
    row.cancel_reason = (
        run.cancel_reason.model_dump(mode="json")
        if run.cancel_reason is not None
        else None
    )
    row.token_usage_prompt = run.token_usage_prompt
    row.token_usage_completion = run.token_usage_completion
    row.cost_usd = run.cost_usd
    row.step_count = run.step_count
    row.started_at = run.started_at
    row.completed_at = run.completed_at


def event_row_to_domain(row: RunEventRow) -> RunEvent:
    return RunEvent(
        id=row.id,
        run_id=row.run_id,
        sequence_number=row.sequence_number,
        event_type=row.event_type,
        payload=row.payload,
        occurred_at=row.occurred_at,
    )


def domain_to_event_row(event: RunEvent) -> RunEventRow:
    """Stores the payload dict verbatim in the JSONB column — the spec
    forbids filtering or re-projection at this boundary."""
    return RunEventRow(
        id=event.id,
        run_id=event.run_id,
        sequence_number=event.sequence_number,
        event_type=event.event_type,
        payload=event.payload,
        occurred_at=event.occurred_at,
    )
