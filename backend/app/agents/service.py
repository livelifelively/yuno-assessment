"""Business logic for the agents module.

Per ADR-009, service functions take and return domain Agent objects — never
DTOs, never rows. The HTTP router does fetch+merge via the HTTP adapter before
calling update_agent.
"""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from app.agents.domain import Agent
from app.agents.errors import AgentEditConflict
from app.agents.persistence import repository
from app.runs import service as runs_service


def get_agent(session: Session, agent_id: UUID) -> Agent | None:
    """Pure read. Returns None for missing — does not raise."""
    return repository.get(session, agent_id)


def list_agents(
    session: Session, *, limit: int = 100, offset: int = 0
) -> tuple[list[Agent], int]:
    """Returns (rows-as-domain, total_count). Total ignores limit/offset."""
    return repository.list_(session, limit=limit, offset=offset)


def create_agent(session: Session, agent: Agent) -> Agent:
    """Persists a new agent. Caller assigns id + created_at/updated_at via the
    HTTP adapter before calling."""
    return repository.create(session, agent)


def update_agent(session: Session, agent: Agent, *, force: bool = False) -> Agent:
    """Persists changes to an existing agent. Calls
    runs_service.list_active_runs_for_agent unless force is True.

    Raises AgentNotFound if agent.id is not in the DB.
    Raises AgentEditConflict if the agent has pending/active runs and force=False.
    """
    if not force:
        active_runs = runs_service.list_active_runs_for_agent(session, agent.id)
        if active_runs:
            raise AgentEditConflict(active_runs=active_runs)
    return repository.update(session, agent)
