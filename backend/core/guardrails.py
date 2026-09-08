"""Generic guardrail evaluation (Stage 2: domain-agnostic core).

A guardrail compares a v1/v2 aggregate of one session-level numeric column
against a fixed threshold. `GuardrailDefinition` describes one guardrail
declaratively — column, how to aggregate it, how to compare — so a domain
registers guardrails as data (a list of these) rather than each guardrail
being its own hand-written check function. This is deliberately NOT a
full rules engine: aggregation and comparison are each a small fixed set
of named strategies, not arbitrary code, per the "keep it simple and
explicit" scope for this stage.

`evaluate_guardrails` is the one general-purpose evaluator every domain's
guardrail list runs through. `GuardrailCheck`/`GuardrailReport` are the
same result types the app has always used (moved here unchanged in shape;
backend.investigation.recommend re-exports both so existing imports keep
working). Nothing here references latency/cost/tool-errors specifically —
those are backend/domains/commerce/guardrails.py's data, describing the
current shopping demo's three guardrails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from backend.analytics.stats.clustering import cluster_arrays

Aggregation = Literal["p95_raw", "cluster_mean"]
Comparison = Literal["ratio", "absolute_increase"]


@dataclass(frozen=True)
class GuardrailDefinition:
    name: str
    column: str
    aggregation: Aggregation
    comparison: Comparison
    threshold: float
    dropna: bool = False


@dataclass
class GuardrailCheck:
    name: str
    v1_value: float
    v2_value: float
    threshold_description: str
    breached: bool


@dataclass
class GuardrailReport:
    checks: list[GuardrailCheck]

    @property
    def any_breach(self) -> bool:
        return any(c.breached for c in self.checks)


def _aggregate(data: pd.DataFrame, column: str, aggregation: Aggregation) -> tuple[float, float]:
    if aggregation == "p95_raw":
        v1 = float(data.loc[data.agent_version == "v1", column].quantile(0.95))
        v2 = float(data.loc[data.agent_version == "v2", column].quantile(0.95))
        return v1, v2
    if aggregation == "cluster_mean":
        arrays = cluster_arrays(data, column) if len(data) else {"v1": [], "v2": []}
        v1 = float(pd.Series(arrays.get("v1", [0])).mean())
        v2 = float(pd.Series(arrays.get("v2", [0])).mean())
        return v1, v2
    raise ValueError(f"unknown aggregation: {aggregation!r}")


def _compare(v1: float, v2: float, comparison: Comparison, threshold: float) -> tuple[bool, str]:
    if comparison == "ratio":
        return bool(v2 > v1 * threshold), f"v2 > v1 x {threshold}"
    if comparison == "absolute_increase":
        return bool(v2 > v1 + threshold), f"v2 > v1 + {threshold}"
    raise ValueError(f"unknown comparison: {comparison!r}")


def evaluate_guardrails(df: pd.DataFrame, definitions: list[GuardrailDefinition]) -> GuardrailReport:
    checks: list[GuardrailCheck] = []
    for gd in definitions:
        data = df.dropna(subset=[gd.column]) if gd.dropna else df
        v1, v2 = _aggregate(data, gd.column, gd.aggregation)
        breached, description = _compare(v1, v2, gd.comparison, gd.threshold)
        checks.append(GuardrailCheck(gd.name, v1, v2, description, breached))
    return GuardrailReport(checks=checks)
