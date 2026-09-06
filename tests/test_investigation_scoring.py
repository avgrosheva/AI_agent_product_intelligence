"""Cluster-aware segment inference, BH correction integration, and
excess-contribution scoring (Stage 2 review requirements #2, #3;
INVESTIGATION.md SS1-SS3)."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.analytics import metric_registry
from backend.analytics.experiment_results import analyze_metric
from backend.analytics.sql_runner import run_sql_file
from backend.investigation.scoring import (
    apply_bh_correction,
    compute_excess_contribution,
    rank_findings,
    run_segment_scan,
)
from backend.investigation.thresholds import TOP_K_FINDINGS


@pytest.fixture(scope="module")
def base_df(db_engine):
    return run_sql_file(db_engine, "session_level_base.sql")


def test_segment_scan_uses_user_level_sample_sizes_everywhere(base_df):
    """Stage 2 review requirement #2: no fallback to session-independent
    inference anywhere in the scan."""
    rows = run_segment_scan(base_df, "abandonment_rate")
    assert len(rows) > 0
    for row in rows:
        assert row.result.n_users_v1 <= row.result.n_sessions_v1
        assert row.result.n_users_v2 <= row.result.n_sessions_v2


def test_segment_scan_matches_direct_analyze_metric_call(base_df):
    """The scan must not reimplement its own inference path — it should
    produce byte-identical results to calling analyze_metric directly with
    the same mask."""
    from backend.investigation.segments import build_segment_registry

    seg = next(s for s in build_segment_registry() if s.label == "platform=android")
    mask = seg.mask_fn(base_df)
    direct = analyze_metric(base_df, metric_registry.get("abandonment_rate"), segment_label=seg.label, segment_mask=mask)

    rows = run_segment_scan(base_df, "abandonment_rate")
    scanned = next(r for r in rows if r.segment.label == "platform=android")

    assert scanned.result.cluster_mean_v1 == direct.cluster_mean_v1
    assert scanned.result.cluster_mean_v2 == direct.cluster_mean_v2
    assert scanned.result.p_value == direct.p_value


def test_bh_correction_only_applied_to_testable_segments(base_df):
    rows = run_segment_scan(base_df, "conversion_rate")
    rows = apply_bh_correction(rows)
    insufficient = [r for r in rows if r.result.verdict == "insufficient_evidence"]
    for r in insufficient:
        assert r.bh_significant is False


def test_bh_correction_is_stricter_than_uncorrected_alpha(base_df):
    """With ~55 simultaneous tests, BH at q=0.10 should reject fewer
    segments than a naive p<0.05 pass would flag as nominally significant —
    demonstrating the correction is actually doing something."""
    rows = run_segment_scan(base_df, "conversion_rate")
    naive_significant = sum(1 for r in rows if r.result.p_value is not None and r.result.p_value < 0.05)
    rows = apply_bh_correction(rows)
    corrected_significant = sum(1 for r in rows if r.bh_significant)
    assert corrected_significant <= naive_significant


def test_excess_contribution_partitions_by_user_share(base_df):
    metric = metric_registry.get("abandonment_rate")
    overall = analyze_metric(base_df, metric)
    rows = run_segment_scan(base_df, "abandonment_rate")
    rows = apply_bh_correction(rows)
    rows = compute_excess_contribution(base_df, rows, "abandonment_rate", overall)
    for row in rows:
        if row.excess_contribution is not None:
            n_segment_users = row.result.n_users_v1 + row.result.n_users_v2
            total_users = base_df["user_id"].nunique()
            expected_share = n_segment_users / total_users
            segment_delta = row.result.cluster_mean_v2 - row.result.cluster_mean_v1
            overall_delta = overall.cluster_mean_v2 - overall.cluster_mean_v1
            assert row.excess_contribution == pytest.approx(expected_share * (segment_delta - overall_delta))


def test_rank_findings_returns_at_most_top_k(base_df):
    metric = metric_registry.get("abandonment_rate")
    overall = analyze_metric(base_df, metric)
    rows = run_segment_scan(base_df, "abandonment_rate")
    rows = apply_bh_correction(rows)
    rows = compute_excess_contribution(base_df, rows, "abandonment_rate", overall)
    top = rank_findings(rows, top_k=TOP_K_FINDINGS)
    assert len(top) <= TOP_K_FINDINGS
    # every returned finding must actually be BH-significant and pass the min-effect filter
    for r in top:
        assert r.bh_significant
        assert r.meets_min_effect
    # ranked descending by |EC|
    ecs = [abs(r.excess_contribution) for r in top]
    assert ecs == sorted(ecs, reverse=True)


def test_rank_findings_excludes_segments_failing_correction():
    from dataclasses import dataclass

    from backend.analytics.experiment_results import MetricResult
    from backend.investigation.scoring import SegmentScanRow
    from backend.investigation.segments import Segment

    fake_result = MetricResult(
        metric_name="conversion_rate", segment="fake", semantic_class="outcome",
        n_sessions_v1=100, n_sessions_v2=100, n_users_v1=50, n_users_v2=50,
        session_value_v1=0.1, session_value_v2=0.2,
        cluster_mean_v1=0.1, cluster_mean_v2=0.2, p_value=0.5, verdict="not_significant",
    )
    fake_segment = Segment(label="fake", dimensions=("requested_category",), values=("laptop",), mask_fn=lambda df: df.index >= 0)
    row = SegmentScanRow(segment=fake_segment, result=fake_result, bh_significant=False, excess_contribution=0.5, meets_min_effect=True)
    assert rank_findings([row], top_k=5) == []
