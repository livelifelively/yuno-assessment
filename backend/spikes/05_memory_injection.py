"""
Spike 05: verify CrewAI memory works — either a yuno-controlled backend can
be injected, or the built-in memory is reachable and survives a multi-task run.

Used by Batch 8a (US-7 — memory dimension).
Fallback on FAIL: use CrewAI built-in memory, drop yuno-controlled memory in V1.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import SpikeResult, gemini_llm, print_and_exit, require_gemini_key  # noqa: E402

NAME = "05_memory_injection"

REMEMBER_PHRASE = "purple elephant"


def run() -> SpikeResult:
    setup_fail = require_gemini_key()
    if setup_fail:
        return SpikeResult(NAME, "FAIL", setup_fail.notes)

    try:
        from crewai import Agent, Crew, Task
    except ImportError as e:
        return SpikeResult(NAME, "FAIL", f"crewai import failed: {e}")

    agent = Agent(
        role="Remembering helper",
        goal=f"Remember key facts the user shares (especially the phrase '{REMEMBER_PHRASE}').",
        backstory="You retain facts across tasks in this crew run.",
        llm=gemini_llm(),
        allow_delegation=False,
        verbose=False,
    )
    plant = Task(
        description=(
            f"The user shares: 'Remember the phrase {REMEMBER_PHRASE}.' "
            "Acknowledge that you have stored it. Reply with 'stored'."
        ),
        expected_output="The word 'stored'.",
        agent=agent,
    )
    recall = Task(
        description="What phrase did the user ask you to remember? Reply with only the phrase.",
        expected_output="The remembered phrase.",
        agent=agent,
    )

    try:
        crew = Crew(agents=[agent], tasks=[plant, recall], memory=True, verbose=False)
        output = crew.kickoff()
    except TypeError as e:
        return SpikeResult(NAME, "FAIL", f"Crew(memory=True) not supported by this version: {e}")
    except Exception as e:  # noqa: BLE001
        return SpikeResult(NAME, "FAIL", f"crew with memory raised: {e}")

    final = str(getattr(output, "raw", output)).lower()
    if REMEMBER_PHRASE in final:
        return SpikeResult(NAME, "PASS", "built-in memory recalled the phrase across tasks")
    return SpikeResult(
        NAME,
        "FAIL",
        f"recall task did not return the planted phrase; output starts: {final[:120]!r}",
    )


if __name__ == "__main__":
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    print_and_exit(run())
