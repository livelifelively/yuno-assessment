"""Compile module — runtime-boundary adapter (yuno.Agent → crewai.Agent).

Per ADR-008 / ADR-009: pure projection function. No DB, no event-bus, no I/O.
Called once per run by the wrapper. See:
- spec:        yuno/3-how/specs/03-architecture/batches/1-single-agent-chat/modules/3-compile.md
- traceability: yuno/3-how/specs/03-architecture/traceability/compile.md

STUB (TDD RED phase). compile_agent raises NotImplementedError until the
GREEN-phase implementation lands per the matrix's Action Items.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.runtime.compile.errors import CompileError

if TYPE_CHECKING:
    import crewai

    from app.agents.domain import Agent


__all__ = ["CompileError", "compile_agent"]


def compile_agent(agent: Agent) -> crewai.Agent:
    """Project domain.Agent's Identity / Personality / Model dimensions into
    a configured crewai.Agent.

    STUB — see Action Items in traceability/compile.md.
    """
    raise NotImplementedError(
        "TODO: compile module — projects domain.Agent → crewai.Agent. "
        "See traceability/compile.md for the implementation punch list."
    )
