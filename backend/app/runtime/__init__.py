"""
CrewAI runtime integration. Stub only in batch 0 — verifies the import surface
and pins the version. Compile (yuno.Agent → crewai.Agent) and wrapper
(pre/post-call enforcement) arrive in batch 1 per ADR-008.
"""

from __future__ import annotations

from importlib import metadata


def crewai_version() -> str:
    try:
        return metadata.version("crewai")
    except metadata.PackageNotFoundError:
        return "not-installed"


def crewai_available() -> bool:
    try:
        import crewai  # noqa: F401
    except ImportError:
        return False
    return True
