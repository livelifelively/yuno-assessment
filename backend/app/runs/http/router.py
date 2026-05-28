"""FastAPI router for /runs endpoints.

Per ADR-009, the router translates request bodies into domain shapes via
the HTTP adapter, delegates business logic to the service, and projects
results back into HTTP DTOs for the response. No business logic lives here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db import get_session
from app.runs import service
from app.runs.domain import RunStatus
from app.runs.errors import (
    AgentNotFoundForRun,
    RunAlreadyTerminal,
    RunNotFound,
)
from app.runs.http import adapter as http_adapter
from app.runs.http.dtos import (
    CancelRequest,
    RunCreate,
    RunEventList,
    RunList,
    RunRead,
)
from app.settings import settings

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunRead, status_code=202)
async def create_run(
    data: RunCreate,
    session: Session = Depends(get_session),
) -> RunRead:
    now = datetime.now(UTC)
    run = http_adapter.create_to_domain(data, id=uuid4(), now=now)
    try:
        result = service.create_run(session, run)
    except AgentNotFoundForRun as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return http_adapter.domain_to_read(result)


@router.post("/{run_id}/cancel", response_model=RunRead, status_code=202)
async def cancel_run(
    run_id: UUID,
    data: CancelRequest | None = None,
    session: Session = Depends(get_session),
) -> RunRead:
    note = data.note if data is not None else None
    try:
        result = service.cancel_run(session, run_id, note)
    except RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RunAlreadyTerminal as exc:
        body = http_adapter.terminal_to_response(exc.status)
        raise HTTPException(
            status_code=409, detail=body.model_dump(mode="json")
        ) from exc
    return http_adapter.domain_to_read(result)


@router.get("", response_model=RunList)
def list_runs(
    status: str | None = None,
    agent_id: UUID | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> RunList:
    # `status` is a single-value filter. Comma-separated values aren't
    # supported in Batch 1 (runs-viewer chips are single-select).
    parsed_status: RunStatus | None
    if status is None:
        parsed_status = None
    else:
        if "," in status:
            raise HTTPException(
                status_code=422,
                detail="status accepts a single value, not a list",
            )
        try:
            parsed_status = RunStatus(status)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=f"unknown status: {status}"
            ) from exc

    if limit is not None and limit > settings.runs_max_list_limit:
        raise HTTPException(
            status_code=422,
            detail=(
                f"limit must be <= {settings.runs_max_list_limit}"
            ),
        )

    items, total = service.list_runs(
        session,
        status=parsed_status,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
    )
    return http_adapter.runs_to_list(items, total)


@router.get("/{run_id}", response_model=RunRead)
def get_run(
    run_id: UUID,
    session: Session = Depends(get_session),
) -> RunRead:
    run = service.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return http_adapter.domain_to_read(run)


@router.get("/{run_id}/events", response_model=RunEventList)
def get_run_events(
    run_id: UUID,
    session: Session = Depends(get_session),
) -> RunEventList:
    try:
        events = service.get_run_events(session, run_id)
    except RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return http_adapter.events_to_list(events)
