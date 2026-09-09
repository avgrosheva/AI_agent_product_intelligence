"""The commerce domain's three registered guardrails (METRICS.md SS5).
Thresholds are unchanged from backend/investigation/thresholds.py — this
module turns the three checks the app has always had into declarative
data, evaluated by the generic backend.core.guardrails.evaluate_guardrails."""

from __future__ import annotations

from backend.core.guardrails import GuardrailDefinition
from backend.investigation.thresholds import (
    GUARDRAIL_COST_RATIO,
    GUARDRAIL_LATENCY_P95_RATIO,
    GUARDRAIL_TOOL_ERROR_ABS_INCREASE,
)

COMMERCE_GUARDRAILS: list[GuardrailDefinition] = [
    GuardrailDefinition(
        name="p95_latency",
        metric="p95_session_latency_ms",
        column="total_latency_ms",
        aggregation="p95_raw",
        kind="ratio",
        direction="increase_is_bad",
        threshold=GUARDRAIL_LATENCY_P95_RATIO,
    ),
    GuardrailDefinition(
        name="tool_error_rate",
        metric="tool_error_rate",
        column="tool_error_rate_session",
        aggregation="cluster_mean",
        kind="absolute",
        direction="increase_is_bad",
        threshold=GUARDRAIL_TOOL_ERROR_ABS_INCREASE,
        dropna=True,
    ),
    GuardrailDefinition(
        name="cost_per_session",
        metric="cost_per_session_usd",
        column="total_cost_usd",
        aggregation="cluster_mean",
        kind="ratio",
        direction="increase_is_bad",
        threshold=GUARDRAIL_COST_RATIO,
    ),
]
