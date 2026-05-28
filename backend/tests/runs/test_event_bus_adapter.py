"""Event-bus adapter tests — pure functions; bus event dict ↔ typed payload
↔ runs domain value."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.event_bus import Event
from app.runs.domain import (
    AbortReason,
    CancelInitiator,
    CancelReason,
    LimitName,
)
from app.runs.event_bus import adapter
from app.runs.event_bus.payloads import RunCancelledPayload
from app.runtime.payloads import (
    LlmCallCompletedPayload,
    LlmCallFailedPayload,
    LlmCallStartedPayload,
    TokenUsage,
)
from app.runtime.wrapper.payloads import (
    AbortReasonPayload,
    RunAbortedPayload,
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
)


def _mk_event(event_type: str, payload: dict) -> Event:
    return Event(type=event_type, payload=payload)


# ---------- Inbound parse_* ----------


def test_parse_run_started_valid_event_returns_payload():
    now = datetime.now(UTC)
    run_id = uuid4()
    event = _mk_event(
        "run.started",
        {"run_id": str(run_id), "occurred_at": now.isoformat()},
    )

    p = adapter.parse_run_started(event)

    assert isinstance(p, RunStartedPayload)
    assert p.run_id == run_id


def test_parse_run_started_missing_run_id_raises():
    event = _mk_event(
        "run.started", {"occurred_at": datetime.now(UTC).isoformat()}
    )
    with pytest.raises(Exception):
        adapter.parse_run_started(event)


def test_parse_run_completed_valid_event_returns_payload():
    event = _mk_event(
        "run.completed",
        {
            "run_id": str(uuid4()),
            "output": "answer",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    p = adapter.parse_run_completed(event)
    assert isinstance(p, RunCompletedPayload)
    assert p.output == "answer"


def test_parse_run_failed_valid_event_returns_payload():
    event = _mk_event(
        "run.failed",
        {
            "run_id": str(uuid4()),
            "error_code": "compile_failed",
            "error_message": "boom",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    p = adapter.parse_run_failed(event)
    assert isinstance(p, RunFailedPayload)
    assert p.error_code == "compile_failed"


def test_parse_run_aborted_valid_event_returns_payload():
    event = _mk_event(
        "run.aborted",
        {
            "run_id": str(uuid4()),
            "abort_reason": {
                "limit": "max_run_tokens",
                "value": 5000.0,
                "cap": 4000.0,
            },
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    p = adapter.parse_run_aborted(event)
    assert isinstance(p, RunAbortedPayload)
    assert p.abort_reason.limit == LimitName.max_run_tokens


def test_parse_run_cancelled_valid_event_returns_payload():
    event = _mk_event(
        "run.cancelled",
        {
            "run_id": str(uuid4()),
            "initiated_by": "operator",
            "requested_at": datetime.now(UTC).isoformat(),
            "note": "stop",
        },
    )
    p = adapter.parse_run_cancelled(event)
    assert isinstance(p, RunCancelledPayload)
    assert p.initiated_by == CancelInitiator.operator


def test_parse_llm_call_started_valid_event_returns_payload():
    event = _mk_event(
        "llm.call.started",
        {
            "run_id": str(uuid4()),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite-preview",
            "step_index": 1,
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    p = adapter.parse_llm_call_started(event)
    assert isinstance(p, LlmCallStartedPayload)
    assert p.step_index == 1


def test_parse_llm_call_completed_valid_event_returns_payload():
    event = _mk_event(
        "llm.call.completed",
        {
            "run_id": str(uuid4()),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite-preview",
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    p = adapter.parse_llm_call_completed(event)
    assert isinstance(p, LlmCallCompletedPayload)
    assert p.usage == TokenUsage(prompt_tokens=10, completion_tokens=4)


def test_parse_llm_call_failed_valid_event_returns_payload():
    event = _mk_event(
        "llm.call.failed",
        {
            "run_id": str(uuid4()),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite-preview",
            "error_code": "provider_timeout",
            "error_message": "boom",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    p = adapter.parse_llm_call_failed(event)
    assert isinstance(p, LlmCallFailedPayload)
    assert p.error_code == "provider_timeout"


# ---------- Inbound projections ----------


def test_abort_reason_from_payload_projects_value_object():
    now = datetime.now(UTC)
    payload = RunAbortedPayload(
        run_id=uuid4(),
        abort_reason=AbortReasonPayload(
            limit=LimitName.daily_cost_usd, value=0.002, cap=0.001
        ),
        occurred_at=now,
    )
    ar = adapter.abort_reason_from_payload(payload)
    assert isinstance(ar, AbortReason)
    assert ar.limit == LimitName.daily_cost_usd
    assert ar.value == 0.002
    assert ar.cap == 0.001


def test_cancel_reason_from_payload_projects_value_object():
    now = datetime.now(UTC)
    payload = RunCancelledPayload(
        run_id=uuid4(),
        initiated_by=CancelInitiator.operator,
        requested_at=now,
        note="stop",
    )
    cr = adapter.cancel_reason_from_payload(payload)
    assert isinstance(cr, CancelReason)
    assert cr.initiated_by == CancelInitiator.operator
    assert cr.requested_at == now
    assert cr.note == "stop"


# ---------- Outbound build + round-trip ----------


def test_build_run_cancelled_payload_is_flat():
    """Payload puts run_id at the top level alongside flat reason fields —
    no nested 'reason' object."""
    run_id = uuid4()
    now = datetime.now(UTC)
    reason = CancelReason(
        initiated_by=CancelInitiator.operator, requested_at=now, note="bye"
    )
    payload = adapter.build_run_cancelled_payload(run_id, reason)

    assert isinstance(payload, RunCancelledPayload)
    assert payload.run_id == run_id
    assert payload.initiated_by == CancelInitiator.operator
    assert payload.requested_at == now
    assert payload.note == "bye"


def test_cancel_reason_round_trip_through_payload_and_back():
    """CancelReason → build → model_dump → parse → cancel_reason_from_payload
    matches the original (modulo round-trip-safe formats)."""
    run_id = uuid4()
    now = datetime.now(UTC)
    original = CancelReason(
        initiated_by=CancelInitiator.operator, requested_at=now, note="stop"
    )

    built = adapter.build_run_cancelled_payload(run_id, original)
    wire = built.model_dump(mode="json")
    event = Event(type="run.cancelled", payload=wire)
    parsed = adapter.parse_run_cancelled(event)
    recovered = adapter.cancel_reason_from_payload(parsed)

    assert recovered.initiated_by == original.initiated_by
    assert recovered.requested_at == original.requested_at
    assert recovered.note == original.note
