"""FastAPI router for /agents endpoints.

Per ADR-009, the router orchestrates fetch+merge via the HTTP adapter and
delegates business logic to the service. Route flow for PUT /agents/{id}:

    repo.get(id) → existing Agent | None         # 404 if None
    http.adapter.apply_update(existing, body)    # merge patch into domain
    service.update_agent(session, updated, force)  # 409 if locked
    http.adapter.domain_to_read(result)          # to response shape
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.agents import service
from app.agents.errors import AgentEditConflict, AgentNotFound
from app.agents.http import adapter as http_adapter
from app.agents.http.dtos import (
    AgentCreate,
    AgentEditBlocked,
    AgentList,
    AgentRead,
    AgentUpdate,
)
from app.db import get_session

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentRead, status_code=201)
def create_agent(
    data: AgentCreate,
    session: Session = Depends(get_session),
) -> AgentRead:
    now = datetime.now(UTC)
    agent = http_adapter.create_to_domain(data, id=uuid4(), now=now)
    result = service.create_agent(session, agent)
    return http_adapter.domain_to_read(result)


@router.get("", response_model=AgentList)
def list_agents(
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> AgentList:
    items, total = service.list_agents(session, limit=limit, offset=offset)
    return AgentList(
        items=[http_adapter.domain_to_read(a) for a in items],
        total=total,
    )


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(
    agent_id: UUID,
    session: Session = Depends(get_session),
) -> AgentRead:
    agent = service.get_agent(session, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return http_adapter.domain_to_read(agent)


@router.put("/{agent_id}", response_model=AgentRead)
def update_agent(
    agent_id: UUID,
    data: AgentUpdate,
    force: bool = False,
    session: Session = Depends(get_session),
) -> AgentRead:
    existing = service.get_agent(session, agent_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    now = datetime.now(UTC)
    updated_domain = http_adapter.apply_update(existing, data, now=now)

    try:
        result = service.update_agent(session, updated_domain, force=force)
    except AgentEditConflict as exc:
        blocked = AgentEditBlocked(
            active_runs=exc.active_runs,
            total=len(exc.active_runs),
        )
        raise HTTPException(
            status_code=409, detail=blocked.model_dump(mode="json")
        ) from exc
    except AgentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return http_adapter.domain_to_read(result)
