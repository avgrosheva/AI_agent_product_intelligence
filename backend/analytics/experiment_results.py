"""User-level experiment analysis: for each implemented, inferential metric
in the registry, compute the session-level descriptive value alongside the
per-user cluster-level significance test, effect size, bootstrap CI, and
full sample-size/event-count accounting (Stage 1 review requirements 1, 2, 8).

This is deliberately NOT the Stage 3 Investigation engine: every metric here
is a single, pre-registered v1-vs-v2 comparison (optionally within one
named, pre-treatment segment), not an automated multi-segment scan. No
Benjamini-Hochberg correction is applied for that reason (STATISTICS.md SS6
scopes BH correction to the automated segment scan specifically).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.analytics.stats.bootstrap import cluster_bootstrap_ci
from backend.analytics.stats.clustering import assert_single_version_per_user, cluster_arrays
from backend.analytics.stats.continuous import mann_whitney_u, welch_t_test
from backend.analytics.stats.effect_size import cohens_d_average_variance, rank_biserial_from_u
# Stage 2 (domain-agnostic core): this binding from metric name to
# session-level column is commerce domain data, not generic logic — lives
# in backend.domains.commerce.metrics and is re-exported here under the
# same name so existing `from backend.analytics.experiment_results import
# METRIC_VALUE_COLUMNS` imports keep working. A non-shopping domain
# supplies its own mapping; analyze_metric() below (the generic mechanism)
# does not change.
from backend.domains.commerce.metrics import METRIC_VALUE_COLUMNS

MIN_USERS_FOR_TEST = 10          # below this: "insufficient evidence", no verdict at all
MIN_USERS_FOR_CLT = 30           # below this (but >= MIN_USERS_FOR_TEST): usable, flagged "small sample"
MIN_EVENTS_FOR_RATE = 10         # STATISTICS.md SS5: need >=10 events AND >=10 non-events, pooled
ALPHA = 0.05


@dataclass
class MetricResult:
    metric_name: str
    segment: str
    semantic_class: str
    n_sessions_v1: int
    n_sessions_v2: int
    n_users_v1: int
    n_users_v2: int
    session_value_v1: float
    session_value_v2: float
    cluster_mean_v1: float | None = None
    cluster_mean_v2: float | None = None
    event_count_v1: int | None = None
    event_count_v2: int | None = None
    non_event_count_v1: int | None = None
    non_event_count_v2: int | None = None
    test_name: str | None = None
    p_value: float | None = None
    effect_size_name: str | None = None
    effect_size_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    ci_stat: str | None = None
    verdict: str = "insufficient_evidence"
    notes: list[str] = field(default_factory=list)


def _apply_segment(df: pd.DataFrame, segment_mask: pd.Series | None) -> pd.DataFrame:
    return df if segment_mask is None else df[segment_mask]


def analyze_metric(
    df: pd.DataFrame,
    metric,  # backend.analytics.metric_registry.MetricDefinition
    segment_label: str = "all sessions",
    segment_mask: pd.Series | None = None,
    metric_value_columns: dict[str, tuple[str, object]] | None = None,
) -> MetricResult:
    """`df` is session_level_base.sql's output (or a segment of it) for the
    commerce domain, or any DomainAdapter.analytics_base_df() output for
    another domain. `metric_value_columns` defaults to the commerce
    binding (METRIC_VALUE_COLUMNS, module-level, unchanged for every
    existing call site) — pass a domain adapter's own
    metric_value_columns() to compute one of ITS metrics instead (Stage 3:
    this is what makes analyze_metric genuinely domain-pluggable, not just
    domain-agnostic in the abstract)."""
    columns = metric_value_columns if metric_value_columns is not None else METRIC_VALUE_COLUMNS
    value_col, eligibility_fn = columns[metric.name]

    scoped = _apply_segment(df, segment_mask)
    eligible = scoped[eligibility_fn(scoped)] if eligibility_fn is not None else scoped
    eligible = eligible.dropna(subset=[value_col])

    n_sessions_v1 = int((scoped.agent_version == "v1").sum())
    n_sessions_v2 = int((scoped.agent_version == "v2").sum())

    session_value_v1 = float(eligible.loc[eligible.agent_version == "v1", value_col].mean()) if (eligible.agent_version == "v1").any() else float("nan")
    session_value_v2 = float(eligible.loc[eligible.agent_version == "v2", value_col].mean()) if (eligible.agent_version == "v2").any() else float("nan")

    result = MetricResult(
        metric_name=metric.name,
        segment=segment_label,
        semantic_class=metric.semantic_class,
        n_sessions_v1=n_sessions_v1,
        n_sessions_v2=n_sessions_v2,
        n_users_v1=0,
        n_users_v2=0,
        session_value_v1=session_value_v1,
        session_value_v2=session_value_v2,
    )

    if eligible.empty:
        result.notes.append("no eligible rows in this segment")
        return result

    assert_single_version_per_user(eligible)
    arrays = cluster_arrays(eligible, value_col)
    v1 = arrays.get("v1", np.array([]))
    v2 = arrays.get("v2", np.array([]))
    result.n_users_v1 = len(v1)
    result.n_users_v2 = len(v2)
    result.cluster_mean_v1 = float(v1.mean()) if len(v1) else None
    result.cluster_mean_v2 = float(v2.mean()) if len(v2) else None

    if metric.is_rate_metric:
        result.event_count_v1 = int(eligible.loc[eligible.agent_version == "v1", value_col].sum())
        result.event_count_v2 = int(eligible.loc[eligible.agent_version == "v2", value_col].sum())
        result.non_event_count_v1 = int((eligible.agent_version == "v1").sum()) - result.event_count_v1
        result.non_event_count_v2 = int((eligible.agent_version == "v2").sum()) - result.event_count_v2

    # --- sparse-data gate (Stage 1 review requirement 8) ---
    if result.n_users_v1 < MIN_USERS_FOR_TEST or result.n_users_v2 < MIN_USERS_FOR_TEST:
        result.verdict = "insufficient_evidence"
        result.notes.append(f"fewer than {MIN_USERS_FOR_TEST} users in at least one arm; no test run")
        return result

    if metric.is_rate_metric:
        total_events = (result.event_count_v1 or 0) + (result.event_count_v2 or 0)
        total_non_events = (result.non_event_count_v1 or 0) + (result.non_event_count_v2 or 0)
        if total_events < MIN_EVENTS_FOR_RATE or total_non_events < MIN_EVENTS_FOR_RATE:
            result.verdict = "insufficient_evidence"
            result.notes.append(
                f"fewer than {MIN_EVENTS_FOR_RATE} pooled events or non-events "
                f"(events={total_events}, non_events={total_non_events}); rate too sparse to test"
            )
            return result

    small_sample = result.n_users_v1 < MIN_USERS_FOR_CLT or result.n_users_v2 < MIN_USERS_FOR_CLT
    if small_sample:
        result.notes.append(f"small sample (n_users v1={result.n_users_v1}, v2={result.n_users_v2}) — wide uncertainty, Mann-Whitney preferred over Welch")

    shape = metric.cluster_stat_shape or "symmetric"
    if shape == "symmetric" and not small_sample:
        test = welch_t_test(v1, v2)
        result.test_name = test["test"]
        result.p_value = test["p_value"]
        result.effect_size_name = "cohens_d_avg_variance"
        result.effect_size_value = cohens_d_average_variance(v1, v2)
        ci = cluster_bootstrap_ci(v1, v2, stat="mean")
    else:
        test = mann_whitney_u(v1, v2)
        result.test_name = test["test"]
        result.p_value = test["p_value"]
        result.effect_size_name = "rank_biserial"
        result.effect_size_value = rank_biserial_from_u(test["statistic"], len(v1), len(v2))
        ci = cluster_bootstrap_ci(v1, v2, stat="median" if shape == "skewed" else "mean")

    result.ci_low = ci["ci_low"]
    result.ci_high = ci["ci_high"]
    result.ci_stat = ci["stat"]
    result.verdict = "significant" if result.p_value is not None and result.p_value < ALPHA else "not_significant"
    return result


def analyze_all_metrics(df: pd.DataFrame, metric_registry: list, segment_label: str = "all sessions", segment_mask: pd.Series | None = None) -> list[MetricResult]:
    results = []
    for metric in metric_registry:
        if not metric.implemented or not metric.is_inferential:
            continue
        if metric.name not in METRIC_VALUE_COLUMNS:
            continue
        results.append(analyze_metric(df, metric, segment_label=segment_label, segment_mask=segment_mask))
    return results


def results_to_dataframe(results: list[MetricResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append(
            {
                "metric": r.metric_name,
                "segment": r.segment,
                "semantic_class": r.semantic_class,
                "n_sessions_v1": r.n_sessions_v1,
                "n_sessions_v2": r.n_sessions_v2,
                "n_users_v1": r.n_users_v1,
                "n_users_v2": r.n_users_v2,
                "session_value_v1": r.session_value_v1,
                "session_value_v2": r.session_value_v2,
                "cluster_mean_v1": r.cluster_mean_v1,
                "cluster_mean_v2": r.cluster_mean_v2,
                "event_count_v1": r.event_count_v1,
                "event_count_v2": r.event_count_v2,
                "test": r.test_name,
                "p_value": r.p_value,
                "effect_size_name": r.effect_size_name,
                "effect_size_value": r.effect_size_value,
                "ci_low": r.ci_low,
                "ci_high": r.ci_high,
                "verdict": r.verdict,
                "notes": "; ".join(r.notes),
            }
        )
    return pd.DataFrame(rows)
