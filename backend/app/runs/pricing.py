"""Provider/model -> (price_in_per_1k_usd, price_out_per_1k_usd) lookup.

Data-driven: adding a new priced model = adding a row to PRICE_TABLE; no
code changes elsewhere. Unknown (provider, model) returns (0.0, 0.0) and
the caller is expected to log a WARNING (see runs/service.accumulate_run_usage).

For Batch 1 this table lives in the runs module — an interim local home.
When the telemetry module (Batch 5) lands, the table moves there and the
runs service swaps the local import for a service call.
"""

from __future__ import annotations

# Provider enum is owned by the agents module's domain; runs reuses it
# rather than redeclaring.
from app.agents.domain import Provider

# Placeholder prices — replace with real provider quotes before shipping.
PRICE_TABLE: dict[tuple[Provider, str], tuple[float, float]] = {
    (Provider.gemini, "gemini-3.1-flash-lite-preview"): (0.0001, 0.0004),
    (Provider.anthropic, "claude-3-5-haiku"): (0.001, 0.005),
}


def price_for(model: str) -> tuple[float, float] | None:
    """Look up per-1k prices for a model name.

    PRICE_TABLE is keyed by `(provider, model)` to be forward-compatible
    with provider-disambiguated pricing; Batch 1 looks up by model name
    only — the subscriber's `llm.call.completed` payload carries model
    directly. Returns None when no row matches — callers default to
    (0.0, 0.0) and log a WARNING per the spec.
    """
    for (_provider, m), price in PRICE_TABLE.items():
        if m == model:
            return price
    return None
