"""Persistence-boundary representation of an agent — flat, column-shaped.

Per ADR-009, translated to/from the domain Agent by
app/agents/persistence/adapter.py. The SQLModel class is `AgentRow` but maps
to the `agents` table (SQLModel's default would be `agentrow`, which doesn't
match the rest of the schema's naming).
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import ConfigDict
from sqlalchemy import Column, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel


class AgentRow(SQLModel, table=True):
    __tablename__ = "agents"
    __table_args__ = (Index("idx_agents_name", "name"),)

    # Pydantic's protected namespace flags any field starting with `model_`;
    # we have three (model_provider, model_name, model_max_output_tokens).
    model_config = ConfigDict(protected_namespaces=())

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(nullable=False)
    role: str | None = Field(default=None, nullable=True)
    description: str | None = Field(default=None, nullable=True)
    system_prompt: str = Field(nullable=False)
    tone: str | None = Field(default=None, nullable=True)
    traits: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    model_provider: str = Field(nullable=False)
    model_name: str = Field(nullable=False)
    temperature: float | None = Field(default=None, nullable=True)
    model_max_output_tokens: int | None = Field(default=None, nullable=True)
    limits: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )
