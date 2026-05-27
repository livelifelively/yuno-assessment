"""Typed errors raised by the agents module."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.runs.domain import RunRef


class AgentNotFound(LookupError):
    """Raised when an operation targets an agent id that is not in the DB."""


class AgentEditConflict(RuntimeError):
    """Raised by update_agent when a non-forced PUT hits a pending/active run.
    Carries the blocking runs so the HTTP layer can serialize them into the
    AgentEditBlocked 409 body."""

    def __init__(self, active_runs: list["RunRef"]) -> None:
        super().__init__(f"Agent has {len(active_runs)} active run(s)")
        self.active_runs = active_runs
