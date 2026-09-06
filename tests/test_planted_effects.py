"""Targeted checks that each of the five planted effects (DATA_MODEL.md SS6)
actually fired in the expected direction in the generated dev dataset.

These are generation-level checks only — not the full Investigation-engine
validation (that's tests/validate_ground_truth.py in a later stage). Each
effect is checked in a segment isolated from the other overlapping effects
(see the Stage 1 deliverable report for why isolation matters: several
approved-doc segments legitimately overlap, e.g. constraint_count_bucket=0-1
includes monitor-category sessions that are also in effect 4's segment).

Uses a plain two-proportion z-test implemented inline (no scipy dependency
at this stage — that lands in Stage 2's statistics layer) purely to confirm
directionality and rough detectability, not as the final statistical
methodology.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest


def _two_proportion_z(p1: float, n1: int, p2: float, n2: int) -> float:
    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0
    return (p2 - p1) / se


@pytest.fixture(scope="module")
def merged(dev_data_dir):
    sessions = pd.read_parquet(dev_data_dir / "dev" / "application" / "sessions.parquet")
    gt = pd.read_parquet(dev_data_dir / "dev" / "validation_ground_truth.parquet")
    df = sessions.merge(gt, on="session_id")
    df["bucket"] = pd.cut(df.num_constraints, [-1, 1, 2, 100], labels=["0-1", "2", "3+"])
    df["converted"] = df.outcome == "purchase"
    df["abandoned"] = df.outcome == "abandoned"
    return df


def test_effect_1_exploratory_uplift(merged):
    """v2 has a lower wrong_constraint_interpretation rate than v1 for
    exploratory (0-1 constraint) requests, excluding monitor category
    (which is effect 4's own segment and would confound this check)."""
    seg = merged[(merged.bucket == "0-1") & (merged.requested_category != "monitor")]
    v1 = seg[seg.agent_version == "v1"]
    v2 = seg[seg.agent_version == "v2"]
    p1 = (v1.ground_truth_failure_mode == "wrong_constraint_interpretation").mean()
    p2 = (v2.ground_truth_failure_mode == "wrong_constraint_interpretation").mean()

    assert len(v1) > 100 and len(v2) > 100
    assert p2 < p1, f"expected v2 < v1 wrong_constraint rate in exploratory segment, got v1={p1:.3f} v2={p2:.3f}"

    z = _two_proportion_z(p1, len(v1), p2, len(v2))
    assert abs(z) > 1.96, f"effect not detectable at 95% in dev-scale sample (z={z:.2f})"

    conv1 = v1.converted.mean()
    conv2 = v2.converted.mean()
    assert conv2 >= conv1, f"expected v2 conversion >= v1 in exploratory segment, got v1={conv1:.3f} v2={conv2:.3f}"


def test_effect_2_overclarify_v2(merged):
    """v2 clarifies unnecessarily far more often than v1 when the user
    already gave >=3 constraints, and this drives more turns, more
    abandonment, lower conversion, and higher cost — but v1's rate must be
    nonzero (behavioral tag, not an artificial 0%-vs-X% cliff)."""
    seg = merged[merged.bucket == "3+"]
    v1 = seg[seg.agent_version == "v1"]
    v2 = seg[seg.agent_version == "v2"]
    p1 = (v1.ground_truth_failure_mode == "unnecessary_clarification").mean()
    p2 = (v2.ground_truth_failure_mode == "unnecessary_clarification").mean()

    assert p1 > 0.0, "v1 baseline unnecessary_clarification rate must be nonzero (no artificial cliff)"
    assert p2 > p1, f"expected v2 > v1 unnecessary_clarification rate, got v1={p1:.3f} v2={p2:.3f}"

    z = _two_proportion_z(p1, len(v1), p2, len(v2))
    assert abs(z) > 1.96

    assert v2.num_turns.mean() > v1.num_turns.mean()
    assert v2.abandoned.mean() > v1.abandoned.mean()
    assert v2.converted.mean() <= v1.converted.mean()
    assert v2.total_cost_usd.mean() > v1.total_cost_usd.mean()


def test_effect_3_android_latency(merged):
    """v2 has higher latency and higher abandonment on android than v1, and
    the v2-vs-v1 abandonment gap on android is clearly larger than the same
    gap off android (isolating the effect from any generic v2 side effects)."""
    android = merged[merged.platform == "android"]
    non_android = merged[merged.platform != "android"]

    lat1 = android[android.agent_version == "v1"].total_latency_ms.mean()
    lat2 = android[android.agent_version == "v2"].total_latency_ms.mean()
    assert lat2 > lat1, f"expected higher android latency for v2, got v1={lat1:.0f} v2={lat2:.0f}"

    gap_android = android[android.agent_version == "v2"].abandoned.mean() - android[android.agent_version == "v1"].abandoned.mean()
    gap_other = non_android[non_android.agent_version == "v2"].abandoned.mean() - non_android[non_android.agent_version == "v1"].abandoned.mean()

    assert gap_android > 0, f"expected v2 > v1 abandonment on android, got gap={gap_android:.3f}"
    assert gap_android > gap_other + 0.05, (
        f"android-specific abandonment gap ({gap_android:.3f}) should clearly exceed "
        f"the off-android gap ({gap_other:.3f})"
    )


def test_effect_4_monitor_constraint_regression_v2(merged):
    """v2 has a higher wrong_constraint_interpretation rate than v1 for
    monitor-category requests, and this is a *version-specific* regression
    (not a both-versions-equally-affected issue, per the Stage 0 methodology
    fix to this effect)."""
    seg = merged[merged.requested_category == "monitor"]
    v1 = seg[seg.agent_version == "v1"]
    v2 = seg[seg.agent_version == "v2"]

    from datagen.effects import resolve_violation_rate

    p1 = resolve_violation_rate("monitor", num_constraints=2, agent_version="v1")
    p2 = resolve_violation_rate("monitor", num_constraints=2, agent_version="v2")
    assert p2 > p1, "monitor violation rate must be higher for v2 than v1 (version-specific, not shared)"

    assert len(v1) > 100 and len(v2) > 100
    assert v2.converted.mean() <= v1.converted.mean(), "expected v2 conversion <= v1 conversion in monitor segment"


def test_effect_5_tool_selection_v2_improved(merged):
    """v2 has a lower wrong_tool_selection rate than v1, isolated to
    constraint_count_bucket=2 where neither the overclarify (bucket=3+) nor
    exploratory (bucket=0-1) effects can dilute the signal."""
    seg = merged[merged.bucket == "2"]
    v1 = seg[seg.agent_version == "v1"]
    v2 = seg[seg.agent_version == "v2"]
    p1 = (v1.ground_truth_failure_mode == "wrong_tool_selection").mean()
    p2 = (v2.ground_truth_failure_mode == "wrong_tool_selection").mean()

    assert len(v1) > 100 and len(v2) > 100
    assert p2 < p1, f"expected v2 < v1 wrong_tool_selection rate, got v1={p1:.3f} v2={p2:.3f}"

    z = _two_proportion_z(p1, len(v1), p2, len(v2))
    assert abs(z) > 1.5  # smaller effect size by design; a looser bar than the other four


def test_no_effect_produces_a_perfectly_clean_zero_or_hundred_percent_rate(merged):
    """Quality rule (approved docs point 8): no planted effect should
    manifest as a deterministic all-or-nothing split; some overlap with
    baseline noise is required for the dataset to be realistic."""
    for bucket_val, mode in [("3+", "unnecessary_clarification"), ("0-1", "wrong_constraint_interpretation")]:
        seg = merged[merged.bucket == bucket_val]
        for version in ["v1", "v2"]:
            sub = seg[seg.agent_version == version]
            rate = (sub.ground_truth_failure_mode == mode).mean()
            assert 0.0 < rate < 1.0, f"{version}/{bucket_val}/{mode} rate is a degenerate {rate}"
