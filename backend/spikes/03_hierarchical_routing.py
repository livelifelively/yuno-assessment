"""
Spike 03: verify CrewAI's Hierarchical Process supports custom routing — a
manager agent picks which downstream agent handles the input.

Used by Batch 3 (US-17 — conditional routing in workflow composer).
Fallback on FAIL: do the if/else routing in a yuno-side Python outer loop and
treat CrewAI as a per-branch executor.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import SpikeResult, gemini_llm, print_and_exit, require_gemini_key  # noqa: E402

NAME = "03_hierarchical_routing"


def run() -> SpikeResult:
    setup_fail = require_gemini_key()
    if setup_fail:
        return SpikeResult(NAME, "FAIL", setup_fail.notes)

    try:
        from crewai import Agent, Crew, Process, Task
    except ImportError as e:
        return SpikeResult(NAME, "FAIL", f"crewai import failed: {e}")

    if not hasattr(Process, "hierarchical"):
        return SpikeResult(NAME, "FAIL", "Process.hierarchical does not exist in this crewai version")

    refund_agent = Agent(
        role="Refunds specialist",
        goal="Respond with 'REFUND HANDLED' for any refund request.",
        backstory="Handles only refund cases.",
        llm=gemini_llm(),
        allow_delegation=False,
        verbose=False,
    )
    billing_agent = Agent(
        role="Billing specialist",
        goal="Respond with 'BILLING HANDLED' for any billing question.",
        backstory="Handles only billing cases.",
        llm=gemini_llm(),
        allow_delegation=False,
        verbose=False,
    )

    task = Task(
        description=(
            "A customer says: 'I want a refund for last month's charge.' "
            "Pick the right specialist and have them respond."
        ),
        expected_output="The specialist's single-line response.",
    )

    crew = Crew(
        agents=[refund_agent, billing_agent],
        tasks=[task],
        process=Process.hierarchical,
        manager_llm=gemini_llm(),
        verbose=False,
    )

    try:
        output = crew.kickoff()
    except Exception as e:  # noqa: BLE001
        return SpikeResult(NAME, "FAIL", f"hierarchical kickoff raised: {e}")

    final = str(getattr(output, "raw", output)).upper()
    if "REFUND" in final:
        return SpikeResult(NAME, "PASS", "manager routed to refund agent")
    if "BILLING" in final:
        return SpikeResult(NAME, "FAIL", "manager routed to wrong agent (billing) for a refund query")
    return SpikeResult(NAME, "FAIL", f"output did not match either branch marker: {final[:120]!r}")


if __name__ == "__main__":
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    print_and_exit(run())
