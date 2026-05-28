"""Persistence-adapter tests — pure functions over data, no DB."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.runs.domain import (
    AbortReason,
    CancelInitiator,
    CancelReason,
    LimitName,
    Run,
    RunEvent,
    RunStatus,
)
from app.runs.persistence import adapter
from app.runs.persistence.row import RunEventRow, RunRow


def _make_run(**overrides) -> Run:
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        agent_id=uuid4(),
        status=RunStatus.pending,
        input="hi",
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
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        run_id=uuid4(),
        sequence_number=1,
        event_type="run.started",
        payload={"foo": "bar"},
        occurred_at=now,
    )
    defaults.update(overrides)
    return RunEvent(**defaults)


def _make_row(**overrides) -> RunRow:
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        agent_id=uuid4(),
        status="pending",
        input="hi",
        token_usage_prompt=0,
        token_usage_completion=0,
        cost_usd=0.0,
        step_count=0,
        created_at=now,
    )
    defaults.update(overrides)
    return RunRow(**defaults)


# ---------- RunRow ----------


def test_domain_to_row_serializes_status_enum_and_simple_fields():
    """RunStatus enum is written as its string value; primitive fields land as-is."""
    run = _make_run(
        status=RunStatus.active,
        input="hello",
        token_usage_prompt=10,
        token_usage_completion=4,
        cost_usd=0.0021,
        step_count=2,
    )
    row = adapter.domain_to_row(run)

    assert row.status == "active"
    assert row.input == "hello"
    assert row.token_usage_prompt == 10
    assert row.token_usage_completion == 4
    assert row.cost_usd == 0.0021
    assert row.step_count == 2


def test_domain_to_row_flattens_abort_reason_into_jsonb_dict():
    """AbortReason model_dump()s into a dict bound for the JSONB column."""
    ar = AbortReason(limit=LimitName.daily_cost_usd, value=0.0012, cap=0.001)
    run = _make_run(status=RunStatus.aborted, abort_reason=ar)
    row = adapter.domain_to_row(run)

    assert isinstance(row.abort_reason, dict)
    assert row.abort_reason["limit"] == LimitName.daily_cost_usd.value
    assert row.abort_reason["value"] == 0.0012
    assert row.abort_reason["cap"] == 0.001


def test_domain_to_row_flattens_cancel_reason_into_jsonb_dict():
    cr = CancelReason(
        initiated_by=CancelInitiator.operator,
        requested_at=datetime.now(UTC),
        note="stop",
    )
    run = _make_run(status=RunStatus.cancelled, cancel_reason=cr)
    row = adapter.domain_to_row(run)

    assert isinstance(row.cancel_reason, dict)
    assert row.cancel_reason["initiated_by"] == CancelInitiator.operator.value
    assert row.cancel_reason["note"] == "stop"


def test_row_to_domain_parses_status_string_into_enum():
    row = _make_row(status="completed", output="answer")
    run = adapter.row_to_domain(row)

    assert run.status == RunStatus.completed
    assert run.output == "answer"


def test_row_to_domain_rehydrates_abort_reason_from_jsonb():
    row = _make_row(
        status="aborted",
        abort_reason={
            "limit": "max_run_tokens",
            "value": 4500.0,
            "cap": 4000.0,
        },
    )
    run = adapter.row_to_domain(row)

    assert isinstance(run.abort_reason, AbortReason)
    assert run.abort_reason.limit == LimitName.max_run_tokens
    assert run.abort_reason.value == 4500.0
    assert run.abort_reason.cap == 4000.0


def test_row_to_domain_rehydrates_cancel_reason_from_jsonb():
    now = datetime.now(UTC)
    row = _make_row(
        status="cancelled",
        cancel_reason={
            "initiated_by": "operator",
            "requested_at": now.isoformat(),
            "note": "stop",
        },
    )
    run = adapter.row_to_domain(row)

    assert isinstance(run.cancel_reason, CancelReason)
    assert run.cancel_reason.initiated_by == CancelInitiator.operator
    assert run.cancel_reason.note == "stop"


def test_round_trip_run_row_run_matches_field_for_field():
    """Run → domain_to_row → row_to_domain matches input (including None fields)."""
    ar = AbortReason(limit=LimitName.max_run_steps, value=11.0, cap=10.0)
    original = _make_run(
        status=RunStatus.aborted,
        abort_reason=ar,
        token_usage_prompt=7,
        token_usage_completion=3,
        cost_usd=0.001,
        step_count=10,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    row = adapter.domain_to_row(original)
    recovered = adapter.row_to_domain(row)

    assert recovered.id == original.id
    assert recovered.agent_id == original.agent_id
    assert recovered.status == original.status
    assert recovered.input == original.input
    assert recovered.token_usage_prompt == original.token_usage_prompt
    assert recovered.token_usage_completion == original.token_usage_completion
    assert recovered.cost_usd == original.cost_usd
    assert recovered.step_count == original.step_count
    assert recovered.abort_reason == original.abort_reason
    assert recovered.cancel_reason is None
    assert recovered.output is None
    assert recovered.error_code is None
    assert recovered.error_message is None


def test_apply_domain_to_row_in_place_preserves_orm_identity():
    """apply_domain_to_row mutates the existing instance; does not touch id."""
    row = _make_row(status="pending", input="orig")
    original_identity = id(row)
    original_id = row.id
    original_created = row.created_at

    new_run = _make_run(
        id=row.id,
        agent_id=row.agent_id,
        status=RunStatus.active,
        input="orig",
        started_at=datetime.now(UTC),
    )
    adapter.apply_domain_to_row(row, new_run)

    assert id(row) == original_identity
    assert row.id == original_id
    assert row.created_at == original_created
    assert row.status == "active"
    assert row.started_at == new_run.started_at


# ---------- RunEventRow ----------


def test_domain_to_event_row_stores_payload_verbatim():
    """RunEvent.payload dict survives unchanged into the JSONB column."""
    payload = {"run_id": "x", "nested": {"a": [1, 2, 3]}}
    event = _make_event(payload=payload, event_type="llm.call.completed")
    row = adapter.domain_to_event_row(event)

    assert row.event_type == "llm.call.completed"
    assert row.payload == payload


def test_event_row_to_domain_round_trip():
    """RunEvent → row → RunEvent preserves all fields."""
    original = _make_event(
        sequence_number=42,
        event_type="run.completed",
        payload={"output": "done"},
    )
    row = adapter.domain_to_event_row(original)
    recovered = adapter.event_row_to_domain(row)

    assert recovered.id == original.id
    assert recovered.run_id == original.run_id
    assert recovered.sequence_number == 42
    assert recovered.event_type == "run.completed"
    assert recovered.payload == {"output": "done"}
    assert recovered.occurred_at == original.occurred_at
