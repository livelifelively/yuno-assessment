"""Event-bus boundary adapter — translates bus payloads ↔ runs domain.
STUB (TDD RED phase).

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

_TODO = "TODO: GREEN phase — runs event-bus adapter"


# --- Inbound: parse bus Event into the emitter's typed payload ---


def parse_run_started(event: Event) -> RunStartedPayload:
    raise NotImplementedError(_TODO)


def parse_run_completed(event: Event) -> RunCompletedPayload:
    raise NotImplementedError(_TODO)


def parse_run_failed(event: Event) -> RunFailedPayload:
    raise NotImplementedError(_TODO)


def parse_run_aborted(event: Event) -> RunAbortedPayload:
    raise NotImplementedError(_TODO)


def parse_run_cancelled(event: Event) -> RunCancelledPayload:
    raise NotImplementedError(_TODO)


def parse_llm_call_started(event: Event) -> LlmCallStartedPayload:
    raise NotImplementedError(_TODO)


def parse_llm_call_completed(event: Event) -> LlmCallCompletedPayload:
    raise NotImplementedError(_TODO)


def parse_llm_call_failed(event: Event) -> LlmCallFailedPayload:
    raise NotImplementedError(_TODO)


# --- Inbound: project payload into runs domain values ---


def abort_reason_from_payload(p: RunAbortedPayload) -> AbortReason:
    raise NotImplementedError(_TODO)


def cancel_reason_from_payload(p: RunCancelledPayload) -> CancelReason:
    raise NotImplementedError(_TODO)


# --- Outbound: owned payload construction ---


def build_run_cancelled_payload(
    run_id: UUID, reason: CancelReason
) -> RunCancelledPayload:
    raise NotImplementedError(_TODO)
