"""FastAPI router for /runs endpoints — STUB (TDD RED phase).

Handlers raise NotImplementedError; FastAPI surfaces this as a 500. The
router itself is fully wired (routes registered, response_model set) so
the app starts and OpenAPI introspection works. GREEN phase fills the
handler bodies with the fetch-merge-delegate pattern.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.runs.http.dtos import (
    CancelRequest,
    RunCreate,
    RunEventList,
    RunList,
    RunRead,
)

router = APIRouter(prefix="/runs", tags=["runs"])

_TODO = "TODO: GREEN phase — runs router handler"


@router.post("", response_model=RunRead, status_code=202)
def create_run(
    data: RunCreate,
    session: Session = Depends(get_session),
) -> RunRead:
    raise NotImplementedError(_TODO)


@router.post("/{run_id}/cancel", response_model=RunRead, status_code=202)
def cancel_run(
    run_id: UUID,
    data: CancelRequest | None = None,
    session: Session = Depends(get_session),
) -> RunRead:
    raise NotImplementedError(_TODO)


@router.get("", response_model=RunList)
def list_runs(
    status: str | None = None,
    agent_id: UUID | None = None,
    limit: int | None = None,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> RunList:
    raise NotImplementedError(_TODO)


@router.get("/{run_id}", response_model=RunRead)
def get_run(
    run_id: UUID,
    session: Session = Depends(get_session),
) -> RunRead:
    raise NotImplementedError(_TODO)


@router.get("/{run_id}/events", response_model=RunEventList)
def get_run_events(
    run_id: UUID,
    session: Session = Depends(get_session),
) -> RunEventList:
    raise NotImplementedError(_TODO)
