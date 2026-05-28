"""Repository operations — DB-aware, domain in/out.

Per ADR-009, sits between the service (which only sees domain) and the
persistence adapter (which translates). The only writer to the `runs`
and `run_events` tables.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel import Session, select

from app.runs.domain import ActiveStatus, Run, RunEvent, RunRef, RunStatus
from app.runs.errors import RunNotFound
from app.runs.persistence import adapter
from app.runs.persistence.row import RunEventRow, RunRow


def get(session: Session, run_id: UUID) -> Run | None:
    row = session.get(RunRow, run_id)
    if row is None:
        return None
    return adapter.row_to_domain(row)


def list_(
    session: Session,
    *,
    status: RunStatus | None = None,
    agent_id: UUID | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[Run], int]:
    total = count(session, status=status, agent_id=agent_id)

    stmt = select(RunRow).order_by(RunRow.created_at.desc())
    if status is not None:
        stmt = stmt.where(RunRow.status == status.value)
    if agent_id is not None:
        stmt = stmt.where(RunRow.agent_id == agent_id)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = session.exec(stmt).all()
    return [adapter.row_to_domain(r) for r in rows], total


def count(
    session: Session,
    *,
    status: RunStatus | None = None,
    agent_id: UUID | None = None,
) -> int:
    stmt = sa_select(func.count()).select_from(RunRow)
    if status is not None:
        stmt = stmt.where(RunRow.status == status.value)
    if agent_id is not None:
        stmt = stmt.where(RunRow.agent_id == agent_id)
    return session.execute(stmt).scalar_one()


def list_active_for_agent(session: Session, agent_id: UUID) -> list[RunRef]:
    """Slim SELECT — builds RunRef directly without a full row_to_domain
    round-trip. RunRef carries only { id, status, started_at }."""
    stmt = (
        sa_select(RunRow.id, RunRow.status, RunRow.started_at)
        .where(RunRow.agent_id == agent_id)
        .where(
            RunRow.status.in_(
                (RunStatus.pending.value, RunStatus.active.value)
            )
        )
    )
    rows = session.execute(stmt).all()
    return [
        RunRef(id=r_id, status=ActiveStatus(r_status), started_at=r_started_at)
        for (r_id, r_status, r_started_at) in rows
    ]


def insert(session: Session, run: Run) -> Run:
    row = adapter.domain_to_row(run)
    session.add(row)
    session.commit()
    session.refresh(row)
    return adapter.row_to_domain(row)


def apply_partial(
    session: Session, run_id: UUID, patch: dict[str, Any]
) -> Run:
    """Apply a column-shaped patch dict to an existing row.

    The patch keys speak column names (status string, JSONB dicts for
    abort_reason/cancel_reason, etc.). Callers pre-compose the dict from
    the service. Raises RunNotFound if the row is missing.
    """
    row = session.get(RunRow, run_id)
    if row is None:
        raise RunNotFound(f"Run {run_id} not found")
    for column, value in patch.items():
        setattr(row, column, value)
    session.add(row)
    session.commit()
    session.refresh(row)
    return adapter.row_to_domain(row)


def sum_cost_for_agent_last_n_hours(
    session: Session, agent_id: UUID, hours: int
) -> float:
    """SELECT COALESCE(SUM(cost_usd), 0.0) FROM runs WHERE agent_id=?
    AND completed_at >= NOW() - interval 'N hours'. Backed by
    idx_runs_agent_id_completed_at."""
    threshold = datetime.now().astimezone() - timedelta(hours=hours)
    stmt = (
        sa_select(func.coalesce(func.sum(RunRow.cost_usd), 0.0))
        .where(RunRow.agent_id == agent_id)
        .where(RunRow.completed_at.is_not(None))
        .where(RunRow.completed_at >= threshold)
    )
    return float(session.execute(stmt).scalar_one())


def insert_event(session: Session, event: RunEvent) -> RunEvent:
    row = adapter.domain_to_event_row(event)
    session.add(row)
    session.commit()
    session.refresh(row)
    return adapter.event_row_to_domain(row)


def list_events(session: Session, run_id: UUID) -> list[RunEvent]:
    stmt = (
        select(RunEventRow)
        .where(RunEventRow.run_id == run_id)
        .order_by(RunEventRow.sequence_number)
    )
    rows = session.exec(stmt).all()
    return [adapter.event_row_to_domain(r) for r in rows]


def next_sequence_number(session: Session, run_id: UUID) -> int:
    """MAX(sequence_number) + 1 FOR run_id. Defence-in-depth against
    concurrent inserts is provided by the UNIQUE (run_id, sequence_number)
    constraint at the DB level — concurrent writers race, the loser
    gets IntegrityError and retries via the service helper."""
    current = session.execute(
        sa_select(func.max(RunEventRow.sequence_number)).where(
            RunEventRow.run_id == run_id
        )
    ).scalar_one()
    return (current or 0) + 1
