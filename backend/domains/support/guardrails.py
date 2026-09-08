"""The support domain's registered guardrail(s) — its own choice, using
the same generic evaluate_guardrails() every domain shares."""

from __future__ import annotations

from backend.core.guardrails import GuardrailDefinition

SUPPORT_GUARDRAILS: list[GuardrailDefinition] = [
    GuardrailDefinition(
        name="escalation_rate_guardrail",
        column="escalated",
        aggregation="cluster_mean",
        comparison="absolute_increase",
        threshold=0.05,
    ),
]
