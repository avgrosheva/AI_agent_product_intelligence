"""The five planted, version-specific treatment effects (DATA_MODEL.md SS6).

Every function here is a pure probability/parameter shift applied on top
of baseline stochastic generation — never a hard override of a session's
outcome — so effects are statistically detectable but overlap with noise,
per the approved docs' explicit "no obviously artificial separations"
requirement. session_builder.py calls these in a fixed order and records
which one (if any) fired for a given session for validation_ground_truth
purposes only.
"""

from __future__ import annotations

import math

from datagen.constants import EFFECT_PARAMS


def apply_overclarify_effect(template_weights: dict, agent_version: str, bucket: str) -> dict:
    """Effect 2: v2 over-clarifies when the user already gave >=3 constraints."""
    if not (agent_version == "v2" and bucket == "3+"):
        return template_weights
    params = EFFECT_PARAMS["overclarify_v2"]
    w = dict(template_weights)
    clarify_boost = params["clarify_prob_boost"]
    abandon_boost = params["clarify_then_abandon_boost"]
    total_boost = clarify_boost + abandon_boost
    # take the mass proportionally from simple_success and filtered_success
    donors = ["simple_success", "filtered_success"]
    donor_total = sum(w[d] for d in donors)
    for d in donors:
        share = w[d] / donor_total if donor_total > 0 else 0.0
        w[d] = max(0.0, w[d] - total_boost * share)
    w["clarified_success"] = w.get("clarified_success", 0.0) + clarify_boost
    w["clarify_then_abandon"] = w.get("clarify_then_abandon", 0.0) + abandon_boost
    return w


def apply_tool_selection_effect(template_weights: dict, agent_version: str) -> dict:
    """Effect 5: v2 makes fewer redundant/wrong tool calls."""
    if agent_version != "v2":
        return template_weights
    params = EFFECT_PARAMS["tool_selection_v2_improved"]
    w = dict(template_weights)
    reduction = w["redundant_search_success"] * params["redundant_search_relative_reduction_v2"]
    w["redundant_search_success"] -= reduction
    donors = ["simple_success", "filtered_success"]
    donor_total = sum(w[d] for d in donors)
    for d in donors:
        share = w[d] / donor_total if donor_total > 0 else 0.0
        w[d] += reduction * share
    return w


def apply_exploratory_template_shift(template_weights: dict, agent_version: str, bucket: str) -> dict:
    """Effect 1 (template half): small shift away from abandon templates for v2
    on exploratory (low-constraint) queries."""
    if not (agent_version == "v2" and bucket == "0-1"):
        return template_weights
    params = EFFECT_PARAMS["exploratory_uplift"]
    w = dict(template_weights)
    shift = params["template_shift_to_success"]
    donors = ["dead_end_abandon", "clarify_then_abandon"]
    donor_total = sum(w[d] for d in donors)
    actual_shift = min(shift, donor_total)
    for d in donors:
        share = w[d] / donor_total if donor_total > 0 else 0.0
        w[d] -= actual_shift * share
    recipients = ["simple_success", "filtered_success"]
    for r in recipients:
        w[r] += actual_shift / len(recipients)
    return w


def resolve_violation_rate(category: str, num_constraints: int, agent_version: str) -> float:
    """Effects 1 (antithesis) and 4: probability the agent's product
    selection violates a stated constraint even though a fully-matching
    product exists in the catalog. Monitor-category takes precedence over
    the exploratory-segment rule when both could apply (see PRD.md
    deviations note) since effect 4 is scoped to the category regardless
    of constraint count, while effect 1 only has a non-vacuous lever at
    exactly one stated constraint.
    """
    if category == "monitor":
        p = EFFECT_PARAMS["monitor_constraint_regression_v2"]
        return p["violation_rate_v2"] if agent_version == "v2" else p["violation_rate_v1"]
    if num_constraints == 1:
        p = EFFECT_PARAMS["exploratory_uplift"]
        return p["violation_rate_v2"] if agent_version == "v2" else p["violation_rate_v1"]
    from datagen.constants import BASELINE_VIOLATION_RATE

    return BASELINE_VIOLATION_RATE


def extra_search_latency_ms(rng, platform: str, agent_version: str) -> float:
    """Effect 3: v2 on android has inflated search_products latency."""
    if not (platform == "android" and agent_version == "v2"):
        return 0.0
    params = EFFECT_PARAMS["android_latency"]
    extra = rng.normal(params["search_latency_extra_ms_mean"], params["search_latency_extra_ms_sd"])
    return max(0.0, float(extra))


def latency_abandon_probability(total_latency_ms: float) -> float:
    """Effect 3: logistic dose-response between accumulated session latency
    and abandonment probability. Applies uniformly to every session — the
    android/v2 effect emerges from that segment's latency being
    systematically higher (via extra_search_latency_ms), not from a
    platform-keyed rule here.
    """
    params = EFFECT_PARAMS["android_latency"]
    midpoint = params["abandon_logistic_midpoint_ms"]
    scale = params["abandon_logistic_scale_ms"]
    max_prob = params["abandon_logistic_max_prob"]
    z = (total_latency_ms - midpoint) / scale
    return max_prob / (1.0 + math.exp(-z))
