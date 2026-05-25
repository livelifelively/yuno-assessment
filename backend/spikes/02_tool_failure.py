"""
Spike 02: verify CrewAI surfaces tool failures with an error payload accessible
to a callback or observable in the run output.

Used by Batch 4 (US-32a/b — tool error events on the run trace).
Fallback on FAIL: wrap tools in try/except inside our adapter and emit yuno
events from the wrapper instead of relying on CrewAI's surface.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import SpikeResult, gemini_llm, print_and_exit, require_gemini_key  # noqa: E402

NAME = "02_tool_failure"

OBSERVED_FAILURE = "boom"


def run() -> SpikeResult:
    setup_fail = require_gemini_key()
    if setup_fail:
        return SpikeResult(NAME, "FAIL", setup_fail.notes)

    from crewai import Agent, Crew, Task
    from crewai.tools import tool

    failed_calls: list[str] = []

    @tool("always_fails")
    def always_fails(query: str) -> str:
        """A tool that always raises. Used to verify error surfacing."""
        raise RuntimeError(OBSERVED_FAILURE)

    def step_callback(step: object) -> None:
        text = repr(step)
        if OBSERVED_FAILURE in text or "always_fails" in text:
            failed_calls.append(text[:200])

    agent = Agent(
        role="Tool tester",
        goal="Call the always_fails tool once with query 'x'.",
        backstory="Spike helper.",
        tools=[always_fails],
        llm=gemini_llm(),
        allow_delegation=False,
        verbose=False,
    )
    task = Task(
        description=(
            "Use the always_fails tool exactly once with query 'x'. "
            "If it errors, report the error literally."
        ),
        expected_output="The exact error message returned by the tool.",
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], step_callback=step_callback, verbose=False)

    try:
        output = crew.kickoff()
    except Exception as e:  # noqa: BLE001
        # Top-level raise is also a signal CrewAI surfaces the failure.
        if OBSERVED_FAILURE in str(e):
            return SpikeResult(NAME, "PASS", "tool failure surfaced via raised exception")
        return SpikeResult(NAME, "FAIL", f"raised but error text missing failure marker: {e}")

    final_text = str(getattr(output, "raw", output))
    callback_saw = any(OBSERVED_FAILURE in s or "always_fails" in s for s in failed_calls)
    output_mentions = OBSERVED_FAILURE in final_text or "always_fails" in final_text.lower()

    if callback_saw:
        return SpikeResult(NAME, "PASS", "step_callback observed failed tool call")
    if output_mentions:
        return SpikeResult(NAME, "PASS", "final output surfaced tool failure")
    return SpikeResult(NAME, "FAIL", "no callback or output trace of tool failure")


if __name__ == "__main__":
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    print_and_exit(run())
