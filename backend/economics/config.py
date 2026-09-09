"""EconomicsConfig: which analytics_base_df columns a domain uses for
cost/success/value — declared by DomainAdapter.economics_config()."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EconomicsConfig:
    # Per-session cost column (e.g. commerce's total_cost_usd, or a
    # support "cost_usd" metric ingested per session). None if this
    # domain has no cost data at all.
    cost_column: str | None
    # 0/1 column marking a successful outcome (commerce: "converted";
    # support: "resolved"). Always required — economics is meaningless
    # without a definition of "success."
    success_column: str
    # Per-session revenue/value column, counted only for successful
    # sessions (e.g. commerce's revenue_usd). None if unavailable — the
    # business-impact figure is then null, never invented (Stage 7 task 6).
    value_column: str | None = None
