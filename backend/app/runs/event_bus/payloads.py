"""Bus payload(s) owned by the runs module.

Other inbound payload types (run.started / completed / failed / aborted from
wrapper, llm.call.* from runtime) live in their emitting modules; the runs
event-bus adapter imports them for inbound parsing.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.runs.domain import CancelInitiator


class RunCancelledPayload(BaseModel):
    """Wire shape of the `run.cancelled` event.

    Owned by runs because the module both publishes (from cancel_run) and
    subscribes (to transition the row). Intentionally flat — no nested
    `reason: CancelReason` — to keep cross-language consumers simple.
    """

    run_id: UUID
    initiated_by: CancelInitiator
    requested_at: datetime
    note: str | None = None
