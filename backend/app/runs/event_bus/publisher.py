"""Outbound event-bus entry point — publishes `run.cancelled`."""

from __future__ import annotations

from uuid import UUID

from app.event_bus import Event, EventBus
from app.runs.domain import CancelReason
from app.runs.event_bus import adapter


async def publish_run_cancelled(
    bus: EventBus, run_id: UUID, reason: CancelReason
) -> None:
    """Builds the flat RunCancelledPayload and emits it on the bus."""
    payload = adapter.build_run_cancelled_payload(run_id, reason)
    await bus.publish(
        Event(type="run.cancelled", payload=payload.model_dump(mode="json"))
    )
