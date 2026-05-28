"""Inbound event-bus entry point — STUB (TDD RED phase).

register() / unregister() are no-op stubs so app startup + shutdown
succeed. _on_run_event raises NotImplementedError; the bus's _safe_call
catches and logs, so publish() returns normally and tests can observe
that the row state was NOT mutated (the RED assertion).
"""

from __future__ import annotations

from app.event_bus import Event, EventBus

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

_TODO = "TODO: GREEN phase — runs event subscriber"


class RunsEventSubscriber:
    """Translates bus events into row updates via the service.

    Stateless aside from the optional bus reference held for unregister.
    """

    def __init__(self) -> None:
        self._bus: EventBus | None = None

    def register(self, bus: EventBus) -> None:
        """Subscribe _on_run_event to every type in SUBSCRIBED_EVENT_TYPES.
        GREEN phase fills the body; the stub records the bus so unregister
        has something to clean up."""
        self._bus = bus

    def unregister(self, bus: EventBus) -> None:
        """Unsubscribe — no-op in the stub."""
        self._bus = None

    async def _on_run_event(self, event: Event) -> None:
        raise NotImplementedError(_TODO)
