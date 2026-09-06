"""Significance tests on per-user cluster statistics (STATISTICS.md SS3).

Exactly two tests are used, chosen per-metric by declared shape (see
metric_registry.py's `cluster_stat_shape` field), never both at once —
STATISTICS.md SS3 explicitly drops the earlier draft's redundant
"run two tests and report both CIs" approach as unnecessary complexity.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def welch_t_test(v1: np.ndarray, v2: np.ndarray) -> dict:
    """For roughly-symmetric cluster statistics (conversion/task-success
    rate, latency, turns — STATISTICS.md SS3 table row 1)."""
    result = stats.ttest_ind(v1, v2, equal_var=False)
    return {"test": "welch_t", "statistic": float(result.statistic), "p_value": float(result.pvalue)}


def mann_whitney_u(v1: np.ndarray, v2: np.ndarray) -> dict:
    """For skewed/outlier-prone cluster statistics (cost, revenue,
    time-to-goal — STATISTICS.md SS3 table row 2)."""
    result = stats.mannwhitneyu(v1, v2, alternative="two-sided")
    return {"test": "mann_whitney_u", "statistic": float(result.statistic), "p_value": float(result.pvalue)}
