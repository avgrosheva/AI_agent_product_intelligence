"""Effect sizes matched to the test that produced the p-value (STATISTICS.md SS8)."""

from __future__ import annotations

import numpy as np


def cohens_d_average_variance(v1: np.ndarray, v2: np.ndarray) -> float:
    """Cohen's d using the unweighted average-variance denominator, the
    consistent companion to Welch's t-test (no equal-variance assumption) —
    NOT the classic n-weighted pooled-SD form, which would assume equal
    variances and contradict Welch's own premise (see STATISTICS.md SS8 for
    why an earlier draft's pairing was inconsistent).
    """
    mean_diff = float(np.mean(v2) - np.mean(v1))
    avg_var = (np.var(v1, ddof=1) + np.var(v2, ddof=1)) / 2
    denom = np.sqrt(avg_var)
    if denom == 0:
        return 0.0
    return mean_diff / denom


def rank_biserial_from_u(u_statistic: float, n1: int, n2: int) -> float:
    """Rank-biserial correlation from the Mann-Whitney U statistic
    (companion effect size for mann_whitney_u — STATISTICS.md SS3/SS8).
    Convention: scipy.stats.mannwhitneyu(v1, v2) returns U for v1;
    r > 0 means v2's values tend to rank higher than v1's.
    """
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(1 - (2 * u_statistic) / (n1 * n2))
