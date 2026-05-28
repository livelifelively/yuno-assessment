"""HTTP-adapter tests — pure functions over data, no DB.

RED phase: every test expects the GREEN implementation; until then they
fail because the adapter raises NotImplementedError.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.runs.domain import (
    AbortReason,
    CancelInitiator,
    CancelReason,
    LimitName,
    Run,
    RunEvent,
    RunStatus,
)
from app.runs.http import adapter
from app.runs.http.dtos import RunAlreadyTerminalResponse, RunCreate


def _make_create_dto(**overrides) -> RunCreate:
    """Build a RunCreate DTO with minimal valid defaults; overrides patch fields a test cares about."""
    defaults = dict(agent_id=uuid4(), input="Hello agent")
    defaults.update(overrides)
    return RunCreate(**defaults)


def _make_run(**overrides) -> Run:
    """Build a domain Run with sensible defaults; pending status unless overridden."""
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        agent_id=uuid4(),
        status=RunStatus.pending,
        input="Hello agent",
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
    defaults.update(overrides)
    return Run(**defaults)


def _make_event(**overrides) -> RunEvent:
    """Build a domain RunEvent with sensible defaults; overrides patch fields a test cares about."""
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        run_id=uuid4(),
        sequence_number=1,
        event_type="run.started",
        payload={"run_id": "abc", "occurred_at": now.isoformat()},
        occurred_at=now,
    )
    defaults.update(overrides)
    return RunEvent(**defaults)


# ---------- create_to_domain ----------


def test_create_to_domain_assigns_persistence_owned_fields():
    """create_to_domain populates id / created_at and forces status=pending
    + zero counters + null terminal fields."""
    dto = _make_create_dto()
    run_id = uuid4()
    now = datetime.now(UTC)

    run = adapter.create_to_domain(dto, id=run_id, now=now)

    assert run.id == run_id
    assert run.agent_id == dto.agent_id
    assert run.input == dto.input
    assert run.status == RunStatus.pending
    assert run.token_usage_prompt == 0
    assert run.token_usage_completion == 0
    assert run.cost_usd == 0.0
    assert run.step_count == 0
    assert run.created_at == now
    assert run.started_at is None
    assert run.completed_at is None
    assert run.output is None
    assert run.error_code is None
    assert run.error_message is None
    assert run.abort_reason is None
    assert run.cancel_reason is None


# ---------- domain_to_read ----------


def test_domain_to_read_surfaces_all_fields():
    """Every domain Run field appears on RunRead 1:1."""
    run = _make_run(
        status=RunStatus.completed,
        output="answer",
        token_usage_prompt=10,
        token_usage_completion=4,
        cost_usd=0.0021,
        step_count=2,
        completed_at=datetime.now(UTC),
    )
    read = adapter.domain_to_read(run)

    assert read.id == run.id
    assert read.agent_id == run.agent_id
    assert read.status == RunStatus.completed
    assert read.output == "answer"
    assert read.token_usage_prompt == 10
    assert read.token_usage_completion == 4
    assert read.cost_usd == 0.0021
    assert read.step_count == 2
    assert read.completed_at == run.completed_at


def test_domain_to_read_serializes_abort_reason():
    """When the run is aborted, abort_reason surfaces as a nested object."""
    ar = AbortReason(limit=LimitName.max_run_tokens, value=4200.0, cap=4000.0)
    run = _make_run(status=RunStatus.aborted, abort_reason=ar)
    read = adapter.domain_to_read(run)

    assert read.abort_reason is not None
    assert read.abort_reason.limit == LimitName.max_run_tokens
    assert read.abort_reason.value == 4200.0
    assert read.abort_reason.cap == 4000.0


def test_domain_to_read_serializes_cancel_reason():
    """When the run is cancelled, cancel_reason surfaces as a nested object."""
    cr = CancelReason(
        initiated_by=CancelInitiator.operator,
        requested_at=datetime.now(UTC),
        note="stopping to edit",
    )
    run = _make_run(status=RunStatus.cancelled, cancel_reason=cr)
    read = adapter.domain_to_read(run)

    assert read.cancel_reason is not None
    assert read.cancel_reason.initiated_by == CancelInitiator.operator
    assert read.cancel_reason.note == "stopping to edit"


# ---------- event_to_read ----------


def test_event_to_read_mirrors_all_fields():
    """RunEvent → RunEventRead is a 1:1 mirror including the verbatim payload dict."""
    payload = {"run_id": "x", "extra": {"nested": [1, 2]}}
    event = _make_event(payload=payload)
    read = adapter.event_to_read(event)

    assert read.id == event.id
    assert read.run_id == event.run_id
    assert read.sequence_number == event.sequence_number
    assert read.event_type == event.event_type
    assert read.payload == payload
    assert read.occurred_at == event.occurred_at


# ---------- runs_to_list / events_to_list ----------


def test_runs_to_list_wraps_items_and_total():
    """(list[Run], total) → RunList { items, total } — total is independent of items."""
    runs = [_make_run() for _ in range(3)]
    rlist = adapter.runs_to_list(runs, total=42)

    assert len(rlist.items) == 3
    assert rlist.total == 42


def test_events_to_list_wraps_items():
    """list[RunEvent] → RunEventList { items } — no pagination wrapper in Batch 1."""
    events = [_make_event(sequence_number=i + 1) for i in range(3)]
    elist = adapter.events_to_list(events)

    assert len(elist.items) == 3
    assert [e.sequence_number for e in elist.items] == [1, 2, 3]


# ---------- terminal_to_response ----------


@pytest.mark.parametrize(
    "status",
    [RunStatus.completed, RunStatus.failed, RunStatus.aborted, RunStatus.cancelled],
)
def test_terminal_to_response_returns_status(status):
    """Each terminal RunStatus produces RunAlreadyTerminalResponse { status }."""
    resp = adapter.terminal_to_response(status)
    assert isinstance(resp, RunAlreadyTerminalResponse)
    assert resp.status == status


# ---------- create → read round trip ----------


def test_round_trip_create_to_read_preserves_input_fields():
    """RunCreate → create_to_domain → domain_to_read produces RunRead whose
    user-supplied fields match the input (plus server-assigned id / counters)."""
    dto = _make_create_dto()
    run_id = uuid4()
    now = datetime.now(UTC)

    run = adapter.create_to_domain(dto, id=run_id, now=now)
    read = adapter.domain_to_read(run)

    assert read.id == run_id
    assert read.agent_id == dto.agent_id
    assert read.input == dto.input
    assert read.status == RunStatus.pending
    assert read.token_usage_prompt == 0
    assert read.cost_usd == 0.0
