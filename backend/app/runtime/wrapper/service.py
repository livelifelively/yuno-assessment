"""WrapperService — STUB (TDD RED phase).

The actual wrapper implementation lands in module 4 of Batch 1. Stubbed here
so that runs.service.create_run can `from app.runtime.wrapper.service import
run_agent` and schedule the background task. Tests monkeypatch this symbol.
"""

from __future__ import annotations

from uuid import UUID


async def run_agent(run_id: UUID) -> None:
    raise NotImplementedError("TODO: wrapper module 4 — drives the agent run")
