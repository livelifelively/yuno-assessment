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
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


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
    "gemini/gemini-2.0-flash",
    "gemini/gemini-1.5-flash",
    "gemini/gemini-1.5-flash-8b",
]


def gemini_llm(model: str | None = None, **kwargs: object):
    from crewai import LLM  # local import keeps import-time cheap

    m = model or _GEMINI_MODELS[0]
    return LLM(model=m, **kwargs)


def print_and_exit(result: SpikeResult) -> None:
    print(result.format())
    sys.exit(0 if result.status == "PASS" else 1)
