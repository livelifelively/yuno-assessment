"""Typed errors raised by the runs module."""

from __future__ import annotations

from app.runs.domain import RunStatus


class RunNotFound(LookupError):
    """Raised by service.get_run_events / service.cancel_run when the
    target run_id is not in the DB."""


class AgentNotFoundForRun(LookupError):
    """Raised by service.create_run when the agent_id in RunCreate does not
    exist. Distinct from agents module's AgentNotFound so the trigger handler
    can map it to the right 404 message."""


class RunAlreadyTerminal(RuntimeError):
    """Raised by service.cancel_run when the target run is already in a
    terminal state. Carries the current RunStatus so the HTTP adapter can
    build the 409 RunAlreadyTerminalResponse body."""

    def __init__(self, status: RunStatus) -> None:
        super().__init__(f"Run is already terminal (status={status.value})")
        self.status = status


class InvalidRunTransition(RuntimeError):
    """Raised by the subscriber's transition path when an event would move
    the row to a state not permitted by the legal-transitions table. Caught
    and logged inside the subscriber — never propagates to the bus caller."""

    def __init__(self, from_status: RunStatus, target: RunStatus) -> None:
        super().__init__(
            f"Illegal transition: {from_status.value} -> {target.value}"
        )
        self.from_status = from_status
        self.target = target
