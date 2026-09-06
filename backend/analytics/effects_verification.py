"""Manual verification of the five planted effects (DATA_MODEL.md SS6) using
ONLY observable application data — never validation_ground_truth.parquet.

This is deliberately not the same thing as Stage 1's generator-validation
script (tests/test_planted_effects.py), which was explicitly scoped as "a
generator sanity check, not production inference" and is not reused here.
This module runs the real Stage 2 methodology (cluster-level tests,
bootstrap CIs, effect sizes) against metrics a human analyst could actually
see in the product today — clarification rate, tool-call counts, latency,
constraint satisfaction — with no failure-mode labels or classifier output
in the loop (those don't exist until Stage 3).

Segments are named, pre-registered, and match the ones INVESTIGATION.md
documents as the target segment for each effect — this module does not
search for them, it looks at the five specific places the approved design
says to look.

Scope boundary for Stage 3: `verify_tool_selection_effect`'s
`has_consecutive_search` pattern (session_level_base.sql) is a one-off,
Stage-2-only descriptive sanity check for a single known template's
signature. Stage 3's trajectory analysis (INVESTIGATION.md SS5) must derive
its own trajectory patterns from agent_actions independently and evaluate
their association with outcomes on its own terms — it must not read this
column or otherwise treat it as a privileged shortcut to the planted
answer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.analytics import metric_registry
from backend.analytics.experiment_results import analyze_metric
from backend.analytics.stats.bootstrap import cluster_bootstrap_ci
from backend.analytics.stats.clustering import cluster_arrays
from backend.analytics.stats.continuous import welch_t_test
from backend.analytics.stats.effect_size import cohens_d_average_variance

EFFECT_CHECKS = [
    {
        "effect": "exploratory_uplift",
        "segment_label": "constraint_count_bucket=0-1, excluding monitor (isolates from effect 4's own segment)",
        "mask_fn": lambda df: (df.constraint_count_bucket == "0-1") & (df.requested_category != "monitor"),
        "metrics": ["conversion_rate", "constraint_satisfaction_rate"],
        "expected_direction": "v2 higher",
    },
    {
        "effect": "overclarify_v2",
        "segment_label": "constraint_count_bucket=3+",
        "mask_fn": lambda df: df.constraint_count_bucket == "3+",
        "metrics": ["unnecessary_clarification_rate", "abandonment_rate", "turns_per_session", "cost_per_session_usd"],
        "expected_direction": "v2 higher",
    },
    {
        "effect": "monitor_constraint_regression_v2",
        "segment_label": "requested_category=monitor",
        "mask_fn": lambda df: df.requested_category == "monitor",
        "metrics": ["constraint_satisfaction_rate", "conversion_rate"],
        "expected_direction": "v2 lower",
    },
]


def verify_named_effects(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for check in EFFECT_CHECKS:
        mask = check["mask_fn"](df)
        for metric_name in check["metrics"]:
            metric = metric_registry.get(metric_name)
            result = analyze_metric(df, metric, segment_label=check["segment_label"], segment_mask=mask)
            direction_observed = (
                "v2 higher" if (result.cluster_mean_v2 or 0) > (result.cluster_mean_v1 or 0)
                else "v2 lower" if (result.cluster_mean_v2 or 0) < (result.cluster_mean_v1 or 0)
                else "tie"
            )
            rows.append(
                {
                    "effect": check["effect"],
                    "segment": check["segment_label"],
                    "metric": metric_name,
                    "expected_direction": check["expected_direction"],
                    "observed_direction": direction_observed,
                    "direction_matches": direction_observed == check["expected_direction"],
                    "n_users_v1": result.n_users_v1,
                    "n_users_v2": result.n_users_v2,
                    "cluster_mean_v1": result.cluster_mean_v1,
                    "cluster_mean_v2": result.cluster_mean_v2,
                    "p_value": result.p_value,
                    "effect_size": result.effect_size_value,
                    "ci_low": result.ci_low,
                    "ci_high": result.ci_high,
                    "verdict": result.verdict,
                }
            )
    return pd.DataFrame(rows)


def verify_tool_selection_effect(df: pd.DataFrame) -> dict:
    """Effect 5's mechanism is specifically the redundant_search_success
    template (two `search` actions back to back, no clarification between
    them) — not tool calls or even search-tool calls in general.
    filtered_success also makes 2 tool calls (search + filter), and
    clarified_success also has 2 search actions (but with `clarify` between
    them), so both `tool_calls_per_session` and a plain `search_products`
    call count conflate the actual mechanism with unrelated templates and
    wash the signal out (verified empirically: neither proxy showed the
    expected direction on this dataset). `has_consecutive_search`
    (session_level_base.sql) isolates the exact pattern the effect targets.
    Segment is bucket=2 to stay clear of overclarify_v2's 3+ segment and
    exploratory_uplift's 0-1 segment.

    Stage-2-only descriptive sanity check — see module docstring's Stage 3
    scope boundary. Do not reuse `has_consecutive_search` in the Stage 3
    trajectory-analysis engine.
    """
    seg = df[df.constraint_count_bucket == "2"]
    arrays = cluster_arrays(seg, "has_consecutive_search")
    v1, v2 = arrays.get("v1", np.array([])), arrays.get("v2", np.array([]))
    test = welch_t_test(v1, v2)
    effect_size = cohens_d_average_variance(v1, v2)
    ci = cluster_bootstrap_ci(v1, v2, stat="mean")
    return {
        "effect": "tool_selection_v2_improved",
        "segment": "constraint_count_bucket=2",
        "metric": "has_consecutive_search (rate of sessions with two back-to-back search actions)",
        "n_users_v1": len(v1),
        "n_users_v2": len(v2),
        "cluster_mean_v1": float(v1.mean()) if len(v1) else None,
        "cluster_mean_v2": float(v2.mean()) if len(v2) else None,
        "expected_direction": "v2 lower",
        "observed_direction": "v2 lower" if v2.mean() < v1.mean() else "v2 higher",
        "p_value": test["p_value"],
        "effect_size_cohens_d": effect_size,
        "ci_low": ci["ci_low"],
        "ci_high": ci["ci_high"],
        "verdict": "significant" if test["p_value"] < 0.05 else "not_significant",
    }


def verify_android_latency_effect(df: pd.DataFrame) -> dict:
    """Effect 3 has no natural home in the standard metric registry (it's a
    dose-response claim about latency driving abandonment, not a single
    rate/mean comparison), so it gets a small dedicated check: (a) is mean
    session latency higher for v2 on android, and (b) is the v2-vs-v1
    abandonment gap on android clearly larger than the same gap off android
    (isolating the effect from any generic v2-wide side effects, e.g. the
    extra latency overclarify_v2 itself adds via more actions per session).
    """
    android = df[df.platform == "android"]
    non_android = df[df.platform != "android"]

    lat_arrays = cluster_arrays(android, "total_latency_ms")
    lat_v1, lat_v2 = lat_arrays.get("v1", np.array([])), lat_arrays.get("v2", np.array([]))
    latency_test = welch_t_test(lat_v1, lat_v2)
    latency_effect_size = cohens_d_average_variance(lat_v1, lat_v2)
    latency_ci = cluster_bootstrap_ci(lat_v1, lat_v2, stat="mean")

    aband_android = cluster_arrays(android, "abandoned")
    aband_other = cluster_arrays(non_android, "abandoned")
    gap_android = float(aband_android.get("v2", np.array([0])).mean() - aband_android.get("v1", np.array([0])).mean())
    gap_other = float(aband_other.get("v2", np.array([0])).mean() - aband_other.get("v1", np.array([0])).mean())

    return {
        "effect": "android_latency",
        "segment": "platform=android",
        "n_users_v1": len(lat_v1),
        "n_users_v2": len(lat_v2),
        "mean_latency_ms_v1": float(lat_v1.mean()) if len(lat_v1) else None,
        "mean_latency_ms_v2": float(lat_v2.mean()) if len(lat_v2) else None,
        "latency_p_value": latency_test["p_value"],
        "latency_effect_size_cohens_d": latency_effect_size,
        "latency_ci_low": latency_ci["ci_low"],
        "latency_ci_high": latency_ci["ci_high"],
        "abandonment_gap_v2_minus_v1_on_android": gap_android,
        "abandonment_gap_v2_minus_v1_off_android": gap_other,
        "android_gap_clearly_larger": gap_android > gap_other + 0.05,
        "verdict": "significant" if latency_test["p_value"] < 0.05 and gap_android > gap_other + 0.05 else "not_significant",
    }
