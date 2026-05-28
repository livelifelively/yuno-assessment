"""Persistence-boundary representation of runs + run_events.

Per ADR-009, translated to/from domain Run / RunEvent by
app/runs/persistence/adapter.py. SQLModel class names are RunRow / RunEventRow
but explicit `__tablename__` maps them to `runs` / `run_events` (SQLModel's
defaults `runrow` / `runeventrow` would not match schema convention).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel

from app.runs.domain import RunStatus

_RUNSTATUS_CHECK = ", ".join(f"'{s.value}'" for s in RunStatus)


class RunRow(SQLModel, table=True):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_RUNSTATUS_CHECK})",
            name="ck_runs_status",
        ),
        Index("idx_runs_agent_id_status", "agent_id", "status"),
        Index("idx_runs_agent_id_completed_at", "agent_id", "completed_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    agent_id: UUID = Field(
        sa_column=Column(ForeignKey("agents.id"), nullable=False, index=True)
    )
    status: str = Field(nullable=False)
    input: str = Field(nullable=False)
    output: str | None = Field(default=None, nullable=True)
    error_code: str | None = Field(default=None, nullable=True)
    error_message: str | None = Field(default=None, nullable=True)
    abort_reason: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    cancel_reason: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    token_usage_prompt: int = Field(default=0, nullable=False)
    token_usage_completion: int = Field(default=0, nullable=False)
    cost_usd: float = Field(default=0.0, nullable=False)
    step_count: int = Field(default=0, nullable=False)
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class RunEventRow(SQLModel, table=True):
    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "sequence_number", name="uq_run_events_run_seq"
        ),
        Index("idx_run_events_run_id", "run_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(
        sa_column=Column(ForeignKey("runs.id"), nullable=False)
    )
    sequence_number: int = Field(nullable=False)
    event_type: str = Field(nullable=False)
    payload: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    occurred_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
