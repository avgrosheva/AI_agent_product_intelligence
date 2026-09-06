"""Tests for the user-level experiment-results engine (Stage 2)."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.analytics import metric_registry
from backend.analytics.experiment_results import analyze_all_metrics, analyze_metric, results_to_dataframe
from backend.analytics.sql_runner import run_sql_file


@pytest.fixture(scope="module")
def base_df(db_engine):
    return run_sql_file(db_engine, "session_level_base.sql")


def test_session_level_base_query_matches_session_count(base_df, dev_data_dir):
    sessions = pd.read_parquet(dev_data_dir / "dev" / "application" / "sessions.parquet")
    assert len(base_df) == len(sessions)


def test_conversion_rate_manual_hand_computation_matches(base_df):
    """ROADMAP.md Stage 2 acceptance criterion: a manual query of per-user
    conversion rate by version matches a hand-computed value."""
    metric = metric_registry.get("conversion_rate")
    result = analyze_metric(base_df, metric)

    # Hand-computed: per-user mean of `converted`, then arm mean.
    per_user = base_df.groupby(["user_id", "agent_version"], observed=True)["converted"].mean().reset_index()
    hand_v1 = per_user.loc[per_user.agent_version == "v1", "converted"].mean()
    hand_v2 = per_user.loc[per_user.agent_version == "v2", "converted"].mean()

    assert result.cluster_mean_v1 == pytest.approx(hand_v1)
    assert result.cluster_mean_v2 == pytest.approx(hand_v2)
    assert result.n_users_v1 == per_user.agent_version.eq("v1").sum()
    assert result.n_users_v2 == per_user.agent_version.eq("v2").sum()


def test_every_metric_result_uses_user_level_sample_sizes_not_session_level(base_df):
    """Stage 1 review requirement #1: no raw session-level z-test may be
    used for a product conclusion — every result's n_users must be <=
    n_sessions (strictly less whenever any user has >1 session)."""
    results = analyze_all_metrics(base_df, metric_registry.METRIC_REGISTRY)
    assert len(results) > 0
    for r in results:
        assert r.n_users_v1 <= r.n_sessions_v1
        assert r.n_users_v2 <= r.n_sessions_v2


def test_insufficient_evidence_verdict_on_tiny_segment(base_df):
    """A segment with too few users should refuse to produce a verdict
    rather than run a test on an unreliable sample (Stage 1 review
    requirement #8)."""
    metric = metric_registry.get("conversion_rate")
    tiny_mask = base_df.index < 5  # 5 sessions, definitely under MIN_USERS_FOR_TEST
    result = analyze_metric(base_df, metric, segment_label="tiny", segment_mask=tiny_mask)
    assert result.verdict == "insufficient_evidence"
    assert result.p_value is None


def test_rate_metrics_report_event_and_non_event_counts(base_df):
    metric = metric_registry.get("conversion_rate")
    result = analyze_metric(base_df, metric)
    assert result.event_count_v1 is not None
    assert result.event_count_v2 is not None
    assert result.non_event_count_v1 is not None
    assert result.event_count_v1 + result.non_event_count_v1 == result.n_sessions_v1


def test_results_to_dataframe_has_expected_columns(base_df):
    results = analyze_all_metrics(base_df, metric_registry.METRIC_REGISTRY)
    df = results_to_dataframe(results)
    for col in ["metric", "segment", "n_users_v1", "n_users_v2", "p_value", "effect_size_value", "ci_low", "ci_high", "verdict"]:
        assert col in df.columns


def test_no_metric_uses_a_post_treatment_dimension_to_define_its_own_segment():
    """Sanity check on the registry itself: metrics whose eligibility is a
    segment filter must only filter on pre-treatment or the metric's own
    outcome column, never on a mechanism variable from a *different*
    metric (that would be circular/leaky segmentation)."""
    from backend.analytics.experiment_results import METRIC_VALUE_COLUMNS

    pre_treatment_names = {m.name for m in metric_registry.pre_treatment_dimensions()}
    assert {"requested_category", "constraint_count_bucket", "platform", "device_tier", "locale", "persona"} == pre_treatment_names
