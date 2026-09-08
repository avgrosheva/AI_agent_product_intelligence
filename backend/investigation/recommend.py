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
# Stage 2 (domain-agnostic core): GuardrailCheck/GuardrailReport/
# evaluate_guardrails are now generic (backend.core.guardrails) —
# re-exported here so existing `from backend.investigation.recommend
# import GuardrailCheck, GuardrailReport` imports keep working.
# check_guardrails() below is now a thin call into evaluate_guardrails()
# with the commerce domain's three guardrail definitions
# (backend.domains.commerce.guardrails) instead of three hand-written
# checks — same columns, same thresholds, same output shape.
from backend.core.guardrails import GuardrailCheck, GuardrailReport, evaluate_guardrails
from backend.domains.commerce.guardrails import COMMERCE_GUARDRAILS
from backend.domains.commerce.next_actions import NEXT_ACTION_TEMPLATES

__all__ = [
    "GuardrailCheck",
    "GuardrailReport",
    "Recommendation",
    "check_guardrails",
    "synthesize_recommendation",
    "NEXT_ACTION_TEMPLATES",
]


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
    return evaluate_guardrails(df, COMMERCE_GUARDRAILS)


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
