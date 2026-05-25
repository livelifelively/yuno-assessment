"""
Spike 04: verify a CrewAI Crew can be re-invoked across iterations and pass
prior output as input — i.e. a feedback loop is expressible.

Used by Batch 3 (US-18 — conditional back-edges / feedback loops).
Fallback on FAIL: pass loop state via task input directly from a yuno-side
outer Python loop, not relying on CrewAI iteration support.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import SpikeResult, gemini_llm, print_and_exit, require_gemini_key  # noqa: E402

NAME = "04_loop_context"


def run() -> SpikeResult:
    setup_fail = require_gemini_key()
    if setup_fail:
        return SpikeResult(NAME, "FAIL", setup_fail.notes)

    try:
        from crewai import Agent, Crew, Task
    except ImportError as e:
        return SpikeResult(NAME, "FAIL", f"crewai import failed: {e}")

    counter = Agent(
        role="Counter",
        goal="Increment a single integer by 1. Respond with only the new integer.",
        backstory="Atomic increment helper.",
        llm=gemini_llm(),
        allow_delegation=False,
        verbose=False,
    )

    def task_with_input(current: str) -> Task:
        return Task(
            description=(
                f"The current value is {current}. "
                "Respond with the integer that is one greater. No prose."
            ),
            expected_output="A single integer.",
            agent=counter,
        )

    value = "0"
    iterations: list[str] = []
    for i in range(3):
        crew = Crew(agents=[counter], tasks=[task_with_input(value)], verbose=False)
        try:
            output = crew.kickoff()
        except Exception as e:  # noqa: BLE001
            return SpikeResult(NAME, "FAIL", f"iteration {i} raised: {e}")

        raw = str(getattr(output, "raw", output)).strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            return SpikeResult(NAME, "FAIL", f"iteration {i} returned no digit: {raw!r}")
        value = digits
        iterations.append(value)

    try:
        as_ints = [int(v) for v in iterations]
    except ValueError:
        return SpikeResult(NAME, "FAIL", f"non-integer in iteration outputs: {iterations}")

    if as_ints == sorted(as_ints) and as_ints[-1] >= as_ints[0] + 1:
        return SpikeResult(NAME, "PASS", f"loop state carried across 3 iterations: {as_ints}")
    return SpikeResult(NAME, "FAIL", f"iterations did not show monotonic progress: {as_ints}")


if __name__ == "__main__":
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    print_and_exit(run())
