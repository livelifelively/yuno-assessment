"""
Shared helpers for batch 0 CrewAI capability spikes.

Each spike is a standalone script that:
- Verifies one CrewAI capability a later batch depends on
- Prints `PASS: <name>` or `FAIL: <name> - <reason>`
- Exits 0 (PASS) or 1 (FAIL) when run directly
- Exposes `run()` returning a SpikeResult for run_all.py
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# gemini-3.1-flash-lite-preview free tier: 15 RPM, 250k TPM, 1000 RPD.
# We enforce a minimum gap between consecutive LLM calls so run_all stays
# comfortably under the 15 RPM ceiling regardless of how many calls each
# spike makes internally.
_MIN_SECONDS_BETWEEN_CALLS = 5  # ≤ 12 calls/min → well under 15 RPM
_last_call_at: float = 0.0


def _rate_limit() -> None:
    global _last_call_at
    elapsed = time.monotonic() - _last_call_at
    wait = _MIN_SECONDS_BETWEEN_CALLS - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.monotonic()


@dataclass(slots=True)
class SpikeResult:
    name: str
    status: str  # "PASS" | "FAIL"
    notes: str = ""

    def format(self) -> str:
        line = f"{self.status}: {self.name}"
        if self.notes:
            line += f" - {self.notes}"
        return line


def require_gemini_key() -> SpikeResult | None:
    if not os.getenv("GEMINI_API_KEY"):
        return SpikeResult("setup", "FAIL", "GEMINI_API_KEY is not set; spikes require a Gemini key")
    return None


_GEMINI_MODELS = [
    "gemini/gemini-3.1-flash-lite-preview",  # free tier: 15 RPM / 250k TPM / 1000 RPD
]


def gemini_llm(model: str | None = None, **kwargs: object):
    from crewai import LLM  # local import keeps import-time cheap

    _rate_limit()
    m = model or _GEMINI_MODELS[0]
    return LLM(model=m, **kwargs)


def print_and_exit(result: SpikeResult) -> None:
    print(result.format())
    sys.exit(0 if result.status == "PASS" else 1)
