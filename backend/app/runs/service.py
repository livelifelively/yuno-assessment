"""Runs service stub — only exposes the surface that the agents module needs
in Batch 1 for the PUT /agents/{id} lock query.

The full runs module is implemented later; see the note on the runs module
README for the ADR-009 alignment plan.

Until the runs module ships, list_active_runs_for_agent returns an empty list,
meaning no agent edit is blocked by an active run. Tests for the agent-edit
lock monkeypatch this function to simulate active runs.
"""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from app.runs.domain import RunRef


def list_active_runs_for_agent(session: Session, agent_id: UUID) -> list[RunRef]:
    """Returns runs in pending/active status for an agent. Stub for Batch 1."""
    return []
