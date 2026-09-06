"""The synthetic-data validity check required by ROADMAP.md Stage 2 and
STATISTICS.md SS2: under a NULL with no true version effect but real
within-user correlation, a naive session-level test's false-positive rate
should be inflated (pseudoreplication), while the cluster-aware,
user-level test's false-positive rate should stay near the nominal alpha.

This is the concrete evidence that Stage 1's methodology fix (treating the
user, not the session, as the unit of analysis) is not just a documentation
change but actually changes the statistical outcome.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from backend.analytics.stats.continuous import welch_t_test


def _simulate_one_rep(rng: np.random.Generator, n_users_per_arm: int, sessions_per_user: int, icc_between_sd: float, within_sd: float) -> pd.DataFrame:
    """No true version effect (null is true): every user's session-level
    values are drawn from the SAME distribution regardless of arm, but
    sessions from the same user share a random user-level effect, inducing
    a nonzero intra-cluster correlation."""
    rows = []
    for arm in ("v1", "v2"):
        for u in range(n_users_per_arm):
            user_effect = rng.normal(0, icc_between_sd)
            for _ in range(sessions_per_user):
                value = user_effect + rng.normal(0, within_sd)
                rows.append({"user_id": f"{arm}_{u}", "agent_version": arm, "value": value})
    return pd.DataFrame(rows)


def _naive_session_level_p_value(df: pd.DataFrame) -> float:
    a = df.loc[df.agent_version == "v1", "value"].to_numpy()
    b = df.loc[df.agent_version == "v2", "value"].to_numpy()
    return float(scipy_stats.ttest_ind(a, b, equal_var=False).pvalue)


def _cluster_level_p_value(df: pd.DataFrame) -> float:
    per_user = df.groupby(["user_id", "agent_version"], observed=True)["value"].mean().reset_index()
    a = per_user.loc[per_user.agent_version == "v1", "value"].to_numpy()
    b = per_user.loc[per_user.agent_version == "v2", "value"].to_numpy()
    return welch_t_test(a, b)["p_value"]


def test_naive_session_level_test_has_inflated_false_positive_rate_under_clustering():
    rng = np.random.default_rng(20260906)
    n_reps = 400
    alpha = 0.05

    naive_rejections = 0
    cluster_rejections = 0
    for _ in range(n_reps):
        df = _simulate_one_rep(rng, n_users_per_arm=60, sessions_per_user=4, icc_between_sd=1.0, within_sd=1.0)
        if _naive_session_level_p_value(df) < alpha:
            naive_rejections += 1
        if _cluster_level_p_value(df) < alpha:
            cluster_rejections += 1

    naive_fpr = naive_rejections / n_reps
    cluster_fpr = cluster_rejections / n_reps

    # The core claim: ignoring clustering meaningfully inflates the false-positive
    # rate; respecting it keeps the rate close to nominal alpha.
    assert naive_fpr > cluster_fpr + 0.10, (
        f"expected the naive session-level test's false-positive rate ({naive_fpr:.3f}) to be "
        f"clearly higher than the cluster-aware test's ({cluster_fpr:.3f}) under a known null with "
        f"injected within-user correlation"
    )
    assert cluster_fpr < 0.12, f"cluster-aware false-positive rate ({cluster_fpr:.3f}) should stay near the nominal 5% (loose bound for {n_reps} reps)"
    assert naive_fpr > 0.20, f"naive false-positive rate ({naive_fpr:.3f}) should be substantially inflated by the injected clustering"
