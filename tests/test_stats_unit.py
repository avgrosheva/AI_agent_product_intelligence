"""Unit tests for backend/analytics/stats/*, checked against scipy/statsmodels
reference implementations and known closed-form results (STATISTICS.md SS10).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as scipy_stats
from statsmodels.stats.multitest import multipletests

from backend.analytics.stats.bootstrap import cluster_bootstrap_ci
from backend.analytics.stats.clustering import (
    assert_single_version_per_user,
    cluster_arrays,
    user_cluster_stat,
)
from backend.analytics.stats.continuous import mann_whitney_u, welch_t_test
from backend.analytics.stats.correction import benjamini_hochberg
from backend.analytics.stats.effect_size import cohens_d_average_variance, rank_biserial_from_u


def test_welch_t_test_matches_scipy_directly():
    rng = np.random.default_rng(1)
    a = rng.normal(0, 1, 200)
    b = rng.normal(0.3, 1.5, 220)
    ours = welch_t_test(a, b)
    ref = scipy_stats.ttest_ind(a, b, equal_var=False)
    assert ours["statistic"] == pytest.approx(ref.statistic)
    assert ours["p_value"] == pytest.approx(ref.pvalue)


def test_mann_whitney_matches_scipy_directly():
    rng = np.random.default_rng(2)
    a = rng.exponential(1.0, 150)
    b = rng.exponential(1.4, 170)
    ours = mann_whitney_u(a, b)
    ref = scipy_stats.mannwhitneyu(a, b, alternative="two-sided")
    assert ours["statistic"] == pytest.approx(ref.statistic)
    assert ours["p_value"] == pytest.approx(ref.pvalue)


def test_cohens_d_known_example():
    # two groups with means 0 and 1, equal variance 1 -> d should be exactly 1
    a = np.array([-1.0, 0.0, 1.0]) + 0.0
    b = np.array([-1.0, 0.0, 1.0]) + 1.0
    d = cohens_d_average_variance(a, b)
    assert d == pytest.approx(1.0, abs=1e-9)


def test_cohens_d_zero_when_no_difference():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = np.array([1.0, 2.0, 3.0, 4.0])
    assert cohens_d_average_variance(a, b) == pytest.approx(0.0)


def test_rank_biserial_sign_convention():
    # v2 strictly greater than v1 everywhere -> U for v1 is 0 -> r should be +1
    v1 = np.array([1.0, 2.0, 3.0])
    v2 = np.array([10.0, 20.0, 30.0])
    result = scipy_stats.mannwhitneyu(v1, v2, alternative="two-sided")
    r = rank_biserial_from_u(result.statistic, len(v1), len(v2))
    assert r == pytest.approx(1.0)

    # reversed: v1 strictly greater -> r should be -1
    result2 = scipy_stats.mannwhitneyu(v2, v1, alternative="two-sided")
    r2 = rank_biserial_from_u(result2.statistic, len(v2), len(v1))
    assert r2 == pytest.approx(-1.0)


def test_benjamini_hochberg_matches_statsmodels():
    rng = np.random.default_rng(3)
    p_values = list(rng.uniform(0, 1, 40))
    p_values[0] = 0.001  # force at least one clear rejection
    p_values[1] = 0.002

    ours = benjamini_hochberg(p_values, q=0.10)
    ref_reject_at_10pct, _, _, _ = multipletests(p_values, alpha=0.10, method="fdr_bh")
    assert ours == list(ref_reject_at_10pct)


def test_benjamini_hochberg_empty_input():
    assert benjamini_hochberg([]) == []


def test_cluster_bootstrap_ci_detects_a_real_difference():
    rng = np.random.default_rng(4)
    v1 = rng.normal(0.20, 0.05, 300)  # e.g. per-user conversion rates
    v2 = rng.normal(0.28, 0.05, 280)
    result = cluster_bootstrap_ci(v1, v2, stat="mean", n_boot=5000, seed=42)
    assert result["point_estimate"] == pytest.approx(0.08, abs=0.02)
    assert result["ci_low"] > 0, "95% CI should exclude 0 for a clear, well-powered difference"


def test_cluster_bootstrap_ci_no_difference_contains_zero():
    rng = np.random.default_rng(5)
    v1 = rng.normal(0.20, 0.05, 300)
    v2 = rng.normal(0.20, 0.05, 300)
    result = cluster_bootstrap_ci(v1, v2, stat="mean", n_boot=5000, seed=42)
    assert result["ci_low"] < 0 < result["ci_high"]


def test_user_cluster_stat_and_cluster_arrays():
    sessions = pd.DataFrame(
        {
            "user_id": ["u1", "u1", "u2", "u2", "u3"],
            "agent_version": ["v1", "v1", "v2", "v2", "v1"],
            "converted": [1, 0, 1, 1, 0],
        }
    )
    per_user = user_cluster_stat(sessions, "converted")
    assert len(per_user) == 3
    u1_rate = per_user.loc[per_user.user_id == "u1", "converted"].iloc[0]
    assert u1_rate == pytest.approx(0.5)

    arrays = cluster_arrays(sessions, "converted")
    assert set(arrays.keys()) == {"v1", "v2"}
    assert len(arrays["v1"]) == 2  # u1, u3
    assert len(arrays["v2"]) == 1  # u2


def test_assert_single_version_per_user_raises_on_violation():
    sessions = pd.DataFrame(
        {
            "user_id": ["u1", "u1"],
            "agent_version": ["v1", "v2"],
        }
    )
    with pytest.raises(ValueError):
        assert_single_version_per_user(sessions)


def test_assert_single_version_per_user_passes_when_consistent():
    sessions = pd.DataFrame(
        {
            "user_id": ["u1", "u1", "u2"],
            "agent_version": ["v1", "v1", "v2"],
        }
    )
    assert_single_version_per_user(sessions) is None
