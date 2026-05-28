"""LLM-call event payloads emitted by the runtime (CrewAI callback bridge).

Owned by the runtime module per the runs spec; defined here in stub form so
the runs event-bus adapter can import them. Full runtime module lands in a
later batch.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TokenUsage(BaseModel):
    """Per-call usage. Carried on LlmCallCompletedPayload.usage."""

    prompt_tokens: int
    completion_tokens: int


class LlmCallStartedPayload(BaseModel):
    run_id: UUID
    provider: str
    model: str
    step_index: int
    occurred_at: datetime


class LlmCallCompletedPayload(BaseModel):
    run_id: UUID
    provider: str
    model: str
    usage: TokenUsage
    occurred_at: datetime
    content: str | None = None
    finish_reason: str | None = None


class LlmCallFailedPayload(BaseModel):
    run_id: UUID
    provider: str
    model: str
    error_code: str
    error_message: str
    occurred_at: datetime
