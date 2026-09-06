"""Deterministic guardrail checks and ship/hold/rollback recommendation
synthesis (INVESTIGATION.md SS6; Stage 2 review requirement #11).

The verdict is produced entirely by explicit rules over already-computed
numbers. An LLMClient may optionally be used to polish the wording of the
next-action sentence — never to choose the verdict, select the guardrail,
or invent the action (AI_EVALUATION.md SS7's numeric-fidelity guardrail
applies: any polished sentence is checked to still contain the same
figures, and falls back to the template on mismatch).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from backend.analytics.experiment_results import MetricResult
from backend.analytics.stats.clustering import cluster_arrays
from backend.investigation.thresholds import (
    GUARDRAIL_COST_RATIO,
    GUARDRAIL_LATENCY_P95_RATIO,
    GUARDRAIL_TOOL_ERROR_ABS_INCREASE,
)

NEXT_ACTION_TEMPLATES = {
    "unnecessary_clarification": "Cap or gate clarification when >=3 explicit constraints are already present; re-run offline evaluation; consider a limited rollout.",
    "wrong_constraint_interpretation": "Audit the constraint-parsing logic for the affected segment; add targeted regression tests; re-run offline evaluation before further rollout.",
    "wrong_tool_selection": "Review the tool-selection policy to reduce redundant tool calls in the affected segment; re-run offline evaluation.",
    "retrieval_failure": "Investigate retrieval/catalog coverage for the affected segment; consider expanding fallback ranking logic.",
    "poor_ranking": "Review ranking quality for the affected segment.",
    "unsupported_product_claim": "Audit agent responses in the affected segment for unsupported claims; tighten grounding.",
    "other": "Manually review a sample of sessions in the affected segment to characterize the regression before further rollout.",
    "none": "Manually review a sample of sessions in the affected segment; no single dominant failure mode was identified.",
}


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


@dataclass
class Recommendation:
    verdict: str  # "ship" | "hold" | "roll_back"
    primary_reason: str
    blocking_guardrails: list[str]
    next_action: str
    rules_applied: list[str] = field(default_factory=list)


def check_guardrails(df: pd.DataFrame) -> GuardrailReport:
    """METRICS.md SS5. Every threshold is a fixed, documented constant —
    no test/p-value involved, matching METRICS.md's own definition of these
    as deterministic ratio-threshold guardrails."""
    checks = []

    p95_v1 = df.loc[df.agent_version == "v1", "total_latency_ms"].quantile(0.95)
    p95_v2 = df.loc[df.agent_version == "v2", "total_latency_ms"].quantile(0.95)
    checks.append(
        GuardrailCheck(
            "p95_latency", float(p95_v1), float(p95_v2),
            f"v2 > v1 x {GUARDRAIL_LATENCY_P95_RATIO}", bool(p95_v2 > p95_v1 * GUARDRAIL_LATENCY_P95_RATIO),
        )
    )

    tool_err = df.dropna(subset=["tool_error_rate_session"])
    arrays = cluster_arrays(tool_err, "tool_error_rate_session") if len(tool_err) else {"v1": [], "v2": []}
    err_v1 = float(pd.Series(arrays.get("v1", [0])).mean())
    err_v2 = float(pd.Series(arrays.get("v2", [0])).mean())
    checks.append(
        GuardrailCheck(
            "tool_error_rate", err_v1, err_v2,
            f"v2 > v1 + {GUARDRAIL_TOOL_ERROR_ABS_INCREASE}", bool(err_v2 > err_v1 + GUARDRAIL_TOOL_ERROR_ABS_INCREASE),
        )
    )

    cost_arrays = cluster_arrays(df, "total_cost_usd")
    cost_v1 = float(pd.Series(cost_arrays.get("v1", [0])).mean())
    cost_v2 = float(pd.Series(cost_arrays.get("v2", [0])).mean())
    checks.append(
        GuardrailCheck(
            "cost_per_session", cost_v1, cost_v2,
            f"v2 > v1 x {GUARDRAIL_COST_RATIO}", bool(cost_v2 > cost_v1 * GUARDRAIL_COST_RATIO),
        )
    )

    return GuardrailReport(checks=checks)


def synthesize_recommendation(
    north_star_result: MetricResult,
    findings: list,  # list[backend.investigation.pipeline.Finding], typed loosely to avoid a circular import
    guardrails: GuardrailReport,
) -> Recommendation:
    """INVESTIGATION.md SS6 decision table, applied in explicit priority
    order to resolve the table's overlap between "north star down" and
    "guardrail breach" rows."""
    rules_applied = []

    north_star_significant = north_star_result.p_value is not None and north_star_result.p_value < 0.05
    north_star_up = north_star_significant and (north_star_result.cluster_mean_v2 or 0) > (north_star_result.cluster_mean_v1 or 0)
    north_star_down = north_star_significant and (north_star_result.cluster_mean_v2 or 0) < (north_star_result.cluster_mean_v1 or 0)

    has_negative_segment = any(f.excess_contribution < 0 for f in findings)  # EC<0 means v2 worse in that segment (see pipeline.py sign convention)

    blocking = [c.name for c in guardrails.checks if c.breached]

    # Priority order resolves the documented table's literal overlap between
    # "north star down" and "guardrail breach with no offsetting improvement":
    # a guardrail breach alone, with a FLAT (not down) north star, is a Hold
    # per the table's second row ("up or flat, but guardrail breached") —
    # Roll back is reserved for a north star that is significantly down.
    # An earlier version of this function treated "guardrail breached and
    # north star not significantly up" as sufficient for roll_back, which
    # incorrectly forced roll_back even when the north star was merely flat
    # (inconclusive) rather than down — exactly the shape this project's own
    # dataset produces, and exactly the shape the brief's own worked example
    # says should be a Hold, not a roll back.
    if north_star_down:
        rules_applied.append("north star significantly down -> roll_back")
        verdict = "roll_back"
    elif north_star_up and not guardrails.any_breach and not has_negative_segment:
        rules_applied.append("north star significantly up, no guardrail breach, no significant negative segment -> ship")
        verdict = "ship"
    elif guardrails.any_breach or has_negative_segment:
        rules_applied.append("north star up or flat, but >=1 guardrail breached or a significant negative segment exists -> hold")
        verdict = "hold"
    else:
        rules_applied.append("no rule matched cleanly; defaulting to hold pending manual review")
        verdict = "hold"

    if findings:
        top = max(findings, key=lambda f: abs(f.excess_contribution))
        primary_reason = (
            f"Largest excess contribution to the regression is segment '{top.segment_label}' "
            f"(EC={top.excess_contribution:.4f}, p={top.p_value:.2e})."
        )
        dominant_mode = top.dominant_failure_mode or "none"
    else:
        primary_reason = "No segment passed the corrected-significance and minimum-effect-size filters for this primary metric."
        dominant_mode = "none"

    next_action = NEXT_ACTION_TEMPLATES.get(dominant_mode, NEXT_ACTION_TEMPLATES["other"])

    return Recommendation(
        verdict=verdict,
        primary_reason=primary_reason,
        blocking_guardrails=blocking,
        next_action=next_action,
        rules_applied=rules_applied,
    )
