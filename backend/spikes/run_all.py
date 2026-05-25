"""
Run all batch 0 CrewAI capability spikes and print a summary table.

Exit 0 iff every spike returns PASS. Loads each spike file via importlib
because filenames start with digits (e.g. `01_llm_tokens.py`) and are not
valid Python identifiers — but the user-stories spec mandates these names.

Usage:
    uv run python spikes/run_all.py
    docker compose run --rm backend uv run python spikes/run_all.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

SPIKES_DIR = Path(__file__).parent
sys.path.insert(0, str(SPIKES_DIR))

from _common import SpikeResult  # noqa: E402

SPIKE_FILES = [
    "01_llm_tokens.py",
    "02_tool_failure.py",
    "03_hierarchical_routing.py",
    "04_loop_context.py",
    "05_memory_injection.py",
]


def load_spike(path: Path):
    name = path.stem  # e.g. "01_llm_tokens" — fine as an internal label
    spec = importlib.util.spec_from_file_location(f"spike_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spike at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    # Allow overriding the model via env var (e.g. when gemini-2.0-flash quota is exhausted)
    from _common import _GEMINI_MODELS

    model_override = os.getenv("SPIKE_GEMINI_MODEL")
    if model_override:
        _GEMINI_MODELS[0] = model_override
        print(f"Using model override: {model_override}")
    results: list[SpikeResult] = []

    for filename in SPIKE_FILES:
        path = SPIKES_DIR / filename
        if not path.exists():
            results.append(SpikeResult(filename, "FAIL", "spike file not found"))
            continue
        try:
            module = load_spike(path)
        except Exception as e:  # noqa: BLE001
            results.append(SpikeResult(filename, "FAIL", f"import error: {e}"))
            continue
        if not hasattr(module, "run"):
            results.append(SpikeResult(filename, "FAIL", "spike has no run() function"))
            continue
        try:
            result = module.run()
        except Exception as e:  # noqa: BLE001
            results.append(SpikeResult(filename, "FAIL", f"run() raised: {e}"))
            continue
        results.append(result)
        print(result.format())

    passed = sum(1 for r in results if r.status == "PASS")
    total = len(results)
    print()
    print(f"== {passed}/{total} PASS ==")

    if passed < total:
        print()
        print("Failures and their documented fallbacks:")
        fallbacks = {
            "01_llm_tokens": "Read usage from LiteLLM response directly.",
            "02_tool_failure": "Wrap tools in try/except in the yuno adapter; emit events from there.",
            "03_hierarchical_routing": "Do if/else routing in a yuno outer loop; CrewAI runs per branch.",
            "04_loop_context": "Pass loop state via task input from a yuno outer loop.",
            "05_memory_injection": "Use CrewAI built-in memory; drop yuno-controlled memory in V1.",
        }
        for r in results:
            if r.status == "FAIL":
                stem = Path(r.name).stem
                print(f"  - {r.name}: {r.notes}")
                print(f"    fallback: {fallbacks.get(stem, '(no documented fallback)')}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
