"""Inbound event-bus entry point — translates each bus event into row updates
via the runs service.

Per ADR-009, the single mutation path for run state after the initial insert.
`_on_run_event` is the dispatcher; one `_handle_*` per event type; then a
uniform `append_run_event` records the event in the audit log.

Session strategy: each invocation opens a session via the injected factory.
Production passes a factory that opens from the engine; tests pass a factory
that yields the test's `db_session` without closing it (so savepoint
isolation works correctly).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from uuid import UUID

from sqlmodel import Session

from app.db import engine as global_engine
from app.event_bus import Event, EventBus
from app.runs import service
from app.runs.domain import RunStatus
from app.runs.errors import InvalidRunTransition, RunNotFound
from app.runs.event_bus import adapter
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

log = logging.getLogger(__name__)


# The eight event types this subscriber listens to. Public so tests can
# iterate without depending on a private attribute.
SUBSCRIBED_EVENT_TYPES: tuple[str, ...] = (
    "run.started",
    "run.completed",
    "run.failed",
    "run.aborted",
    "run.cancelled",
    "llm.call.started",
    "llm.call.completed",
    "llm.call.failed",
)


@contextmanager
def _default_session_factory() -> Iterator[Session]:
    """Production session factory — opens a session from the engine and
    closes it on exit."""
    with Session(global_engine) as session:
        yield session


class RunsEventSubscriber:
    """Translates bus events into row updates via the service.

    Stateless aside from the bus reference (held for unregister) and the
    session factory (set at construction).
    """

    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ) -> None:
        self._session_factory = session_factory or _default_session_factory
        self._bus: EventBus | None = None

    def register(self, bus: EventBus) -> None:
        """Subscribe `_on_run_event` to every type in SUBSCRIBED_EVENT_TYPES."""
        self._bus = bus
        for event_type in SUBSCRIBED_EVENT_TYPES:
            bus.subscribe(event_type, self._on_run_event)

    def unregister(self, bus: EventBus) -> None:
        """Unsubscribe `_on_run_event` from every owned type."""
        for event_type in SUBSCRIBED_EVENT_TYPES:
            bus.unsubscribe(event_type, self._on_run_event)
        self._bus = None

    async def _on_run_event(self, event: Event) -> None:
        """Central dispatcher. Routes by event.type, tolerates per-handler
        errors, and always appends to the audit log when the run exists."""
        try:
            run_id = UUID(event.payload["run_id"])
        except (KeyError, ValueError, TypeError):
            log.error(
                "event %s has no usable run_id; dropping (payload=%r)",
                event.type,
                event.payload,
            )
            return

        with self._session_factory() as session:
            # If the run doesn't exist, log and drop — appending an event
            # row would fail at the FK level and isn't useful anyway.
            if service.get_run(session, run_id) is None:
                log.error(
                    "event %s references unknown run_id %s; dropping",
                    event.type,
                    run_id,
                )
                return

            try:
                self._dispatch(session, event)
            except InvalidRunTransition as exc:
                log.warning(
                    "illegal transition for event %s: %s -> %s; row unchanged",
                    event.type,
                    exc.from_status.value,
                    exc.target.value,
                )
            except Exception:
                log.exception(
                    "unexpected error handling %s; row unchanged", event.type
                )

            # Always record the event (audit log invariant), even when the
            # state-mutation handler rejected the transition.
            try:
                service.append_run_event(session, run_id, event)
            except Exception:
                log.exception(
                    "failed to append event row for %s", event.type
                )

    def _dispatch(self, session: Session, event: Event) -> None:
        match event.type:
            case "run.started":
                self._handle_run_started(session, adapter.parse_run_started(event))
            case "run.completed":
                self._handle_run_completed(
                    session, adapter.parse_run_completed(event)
                )
            case "run.failed":
                self._handle_run_failed(session, adapter.parse_run_failed(event))
            case "run.aborted":
                self._handle_run_aborted(
                    session, adapter.parse_run_aborted(event)
                )
            case "run.cancelled":
                self._handle_run_cancelled(
                    session, event, adapter.parse_run_cancelled(event)
                )
            case "llm.call.started":
                self._handle_llm_call_started(
                    session, adapter.parse_llm_call_started(event)
                )
            case "llm.call.completed":
                self._handle_llm_call_completed(
                    session, adapter.parse_llm_call_completed(event)
                )
            case "llm.call.failed":
                self._handle_llm_call_failed(
                    session, adapter.parse_llm_call_failed(event)
                )
            case _:
                log.warning("subscriber got unowned event type %s; ignoring", event.type)

    # --- per-type handlers ---

    def _handle_run_started(
        self, session: Session, payload: RunStartedPayload
    ) -> None:
        service.transition_run_state(
            session,
            payload.run_id,
            RunStatus.active,
            started_at=payload.occurred_at,
        )

    def _handle_run_completed(
        self, session: Session, payload: RunCompletedPayload
    ) -> None:
        service.transition_run_state(
            session,
            payload.run_id,
            RunStatus.completed,
            output=payload.output,
            completed_at=payload.occurred_at,
        )

    def _handle_run_failed(
        self, session: Session, payload: RunFailedPayload
    ) -> None:
        service.transition_run_state(
            session,
            payload.run_id,
            RunStatus.failed,
            error_code=payload.error_code,
            error_message=payload.error_message,
            completed_at=payload.occurred_at,
        )

    def _handle_run_aborted(
        self, session: Session, payload: RunAbortedPayload
    ) -> None:
        abort_reason = adapter.abort_reason_from_payload(payload)
        service.transition_run_state(
            session,
            payload.run_id,
            RunStatus.aborted,
            abort_reason=abort_reason,
            completed_at=payload.occurred_at,
        )

    def _handle_run_cancelled(
        self,
        session: Session,
        event: Event,
        payload,
    ) -> None:
        # RunCancelledPayload doesn't carry occurred_at (it has requested_at);
        # use the bus Event's own occurred_at for completed_at.
        cancel_reason = adapter.cancel_reason_from_payload(payload)
        service.transition_run_state(
            session,
            payload.run_id,
            RunStatus.cancelled,
            cancel_reason=cancel_reason,
            completed_at=event.occurred_at,
        )

    def _handle_llm_call_started(
        self, session: Session, payload: LlmCallStartedPayload
    ) -> None:
        service.bump_step_count(session, payload.run_id)

    def _handle_llm_call_completed(
        self, session: Session, payload: LlmCallCompletedPayload
    ) -> None:
        service.accumulate_run_usage(
            session, payload.run_id, payload.usage, payload.model
        )

    def _handle_llm_call_failed(
        self, session: Session, payload: LlmCallFailedPayload
    ) -> None:
        # No row mutation — just the event-row insert handled by the
        # outer _on_run_event.
        pass
