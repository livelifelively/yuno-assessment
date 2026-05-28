"""Run lifecycle event payloads emitted by WrapperService.

Owned by the wrapper module per the runs spec; defined here in stub form so
the runs event-bus adapter can import them. The wrapper service that emits
these lands in a later batch (module 4).

`AbortReasonPayload` mirrors the runs-side `AbortReason` value object;
keeping the field shape identical lets the runs adapter project directly.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.runs.domain import LimitName


class AbortReasonPayload(BaseModel):
    """Nested inside RunAbortedPayload. Same field shape as the runs-side
    AbortReason — the runs event-bus adapter projects directly."""

    limit: LimitName
    value: float
    cap: float


class RunStartedPayload(BaseModel):
    run_id: UUID
    occurred_at: datetime


class RunCompletedPayload(BaseModel):
    run_id: UUID
    output: str
    occurred_at: datetime


class RunFailedPayload(BaseModel):
    run_id: UUID
    error_code: str
    error_message: str
    occurred_at: datetime


class RunAbortedPayload(BaseModel):
    run_id: UUID
    abort_reason: AbortReasonPayload
    occurred_at: datetime
