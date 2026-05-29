"""Compile module errors.

Per ADR-009: errors live in errors.py alongside the canonical types.
"""

from __future__ import annotations


class CompileError(ValueError):
    """Raised when domain.Agent cannot be projected to a crewai.Agent.

    Carries the field that failed validation and a short reason. The wrapper's
    top-level handler catches this directly and emits `run.failed` with
    `error_code="compile_failed"` and `error_message=f"{field}: {reason}"`.
    """

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason
