"""Runs domain types exposed for cross-module consumption (Batch 1 surface).

This module pre-dates ADR-009 alignment for the full runs module — see the note
at the top of yuno/3-how/specs/03-architecture/batches/1-single-agent-chat/modules/2-runs/README.md
for the re-evaluation plan. RunRef is defined here because the agents module's
AgentEditBlocked DTO imports it for the 409 response body.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class ActiveStatus(StrEnum):
    pending = "pending"
    active = "active"


class RunRef(BaseModel):
    """Slim reference to an in-flight run. Returned by
    runs.list_active_runs_for_agent for the agents-module lock check."""

    id: UUID
    status: ActiveStatus
    started_at: datetime | None = None
