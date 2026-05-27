"""Repository operations — DB-aware, returns/accepts domain Agent objects.

Per ADR-009, sits between the service (which only sees domain) and the
persistence adapter (which translates).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select as sa_select
from sqlmodel import Session, select

from app.agents.domain import Agent
from app.agents.errors import AgentNotFound
from app.agents.persistence import adapter
from app.agents.persistence.row import AgentRow


def get(session: Session, agent_id: UUID) -> Agent | None:
    row = session.get(AgentRow, agent_id)
    if row is None:
        return None
    return adapter.row_to_domain(row)


def list_(
    session: Session, *, limit: int = 100, offset: int = 0
) -> tuple[list[Agent], int]:
    total = session.execute(
        sa_select(func.count()).select_from(AgentRow)
    ).scalar_one()
    rows = session.exec(
        select(AgentRow).order_by(AgentRow.created_at).offset(offset).limit(limit)
    ).all()
    return [adapter.row_to_domain(r) for r in rows], total


def create(session: Session, agent: Agent) -> Agent:
    row = adapter.domain_to_row(agent)
    session.add(row)
    session.commit()
    session.refresh(row)
    return adapter.row_to_domain(row)


def update(session: Session, agent: Agent) -> Agent:
    """Updates an existing row in place. Raises AgentNotFound if missing."""
    row = session.get(AgentRow, agent.id)
    if row is None:
        raise AgentNotFound(f"Agent {agent.id} not found")
    adapter.apply_domain_to_row(row, agent)
    session.add(row)
    session.commit()
    session.refresh(row)
    return adapter.row_to_domain(row)
