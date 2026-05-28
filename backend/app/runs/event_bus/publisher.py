"""Outbound event-bus entry point — STUB (TDD RED phase)."""

from __future__ import annotations

from uuid import UUID

from app.event_bus import EventBus
from app.runs.domain import CancelReason


async def publish_run_cancelled(
    bus: EventBus, run_id: UUID, reason: CancelReason
) -> None:
    raise NotImplementedError("TODO: GREEN phase — runs publisher")
