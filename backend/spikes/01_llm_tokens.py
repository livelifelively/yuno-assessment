"""
Spike 01: verify a CrewAI run exposes prompt/completion token counts.

Used by Batch 5 (US-30 telemetry).
Fallback on FAIL: read usage from LiteLLM response directly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running as `python spikes/01_llm_tokens.py` or via importlib.
sys.path.insert(0, str(Path(__file__).parent))

from _common import SpikeResult, gemini_llm, print_and_exit, require_gemini_key  # noqa: E402

NAME = "01_llm_tokens"


def run() -> SpikeResult:
    setup_fail = require_gemini_key()
    if setup_fail:
        return SpikeResult(NAME, "FAIL", setup_fail.notes)

    from crewai import Agent, Crew, Task

    agent = Agent(
        role="Echo",
        goal="Reply with a single short word.",
        backstory="Minimal helper for spike tests.",
        llm=gemini_llm(),
        allow_delegation=False,
        verbose=False,
    )
    task = Task(
        description="Say the word 'hello' and nothing else.",
        expected_output="A single word.",
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], verbose=False)
    output = crew.kickoff()

    usage = getattr(output, "token_usage", None)
    if usage is None:
        return SpikeResult(NAME, "FAIL", "CrewOutput has no `token_usage` attribute")

    prompt = _get(usage, "prompt_tokens")
    completion = _get(usage, "completion_tokens")

    if prompt is None or completion is None:
        return SpikeResult(NAME, "FAIL", f"token_usage missing prompt/completion fields: {usage!r}")
    if prompt < 1 or completion < 1:
        return SpikeResult(NAME, "FAIL", f"token counts zero: prompt={prompt}, completion={completion}")

    return SpikeResult(NAME, "PASS", f"prompt={prompt}, completion={completion}")


def _get(obj: object, attr: str) -> int | None:
    val = getattr(obj, attr, None)
    if val is None and isinstance(obj, dict):
        val = obj.get(attr)
    return int(val) if val is not None else None


if __name__ == "__main__":
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    print_and_exit(run())
