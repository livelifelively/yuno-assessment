"""Event-bus boundary adapter — translates bus payloads ↔ runs domain.

Inbound: parse_* functions validate the bus event dict into the emitter's
typed payload model; abort_reason_from_payload / cancel_reason_from_payload
project further into runs-side domain value objects.

Outbound: build_run_cancelled_payload constructs the wire shape from a
domain CancelReason; the publisher serializes via model_dump(mode="json")
and emits onto the bus.
"""

from __future__ import annotations

from uuid import UUID

from app.event_bus import Event
from app.runs.domain import AbortReason, CancelReason
from app.runs.event_bus.payloads import RunCancelledPayload
from app.runtime.payloads import (
    LlmCallCompletedPayload,
    LlmCallFailedPayload,
    LlmCallStartedPayload,
)
from app.runtime.wrapper.payloads import (
    RunAbortedPayload,
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
)


# --- Inbound: parse bus Event into the emitter's typed payload ---


def parse_run_started(event: Event) -> RunStartedPayload:
    return RunStartedPayload.model_validate(event.payload)


def parse_run_completed(event: Event) -> RunCompletedPayload:
    return RunCompletedPayload.model_validate(event.payload)


def parse_run_failed(event: Event) -> RunFailedPayload:
    return RunFailedPayload.model_validate(event.payload)


def parse_run_aborted(event: Event) -> RunAbortedPayload:
    return RunAbortedPayload.model_validate(event.payload)


def parse_run_cancelled(event: Event) -> RunCancelledPayload:
    return RunCancelledPayload.model_validate(event.payload)


def parse_llm_call_started(event: Event) -> LlmCallStartedPayload:
    return LlmCallStartedPayload.model_validate(event.payload)


def parse_llm_call_completed(event: Event) -> LlmCallCompletedPayload:
    return LlmCallCompletedPayload.model_validate(event.payload)


def parse_llm_call_failed(event: Event) -> LlmCallFailedPayload:
    return LlmCallFailedPayload.model_validate(event.payload)


# --- Inbound: project payload into runs domain values ---


def abort_reason_from_payload(p: RunAbortedPayload) -> AbortReason:
    return AbortReason(
        limit=p.abort_reason.limit,
        value=p.abort_reason.value,
        cap=p.abort_reason.cap,
    )


def cancel_reason_from_payload(p: RunCancelledPayload) -> CancelReason:
    return CancelReason(
        initiated_by=p.initiated_by,
        requested_at=p.requested_at,
        note=p.note,
    )


# --- Outbound: owned payload construction ---


def build_run_cancelled_payload(
    run_id: UUID, reason: CancelReason
) -> RunCancelledPayload:
    return RunCancelledPayload(
        run_id=run_id,
        initiated_by=reason.initiated_by,
        requested_at=reason.requested_at,
        note=reason.note,
    )
