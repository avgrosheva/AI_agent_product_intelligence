"""Cluster bootstrap confidence intervals (STATISTICS.md SS4).

Resamples USERS with replacement within each arm, never sessions —
`v1`/`v2` inputs here are already one-row-per-user cluster statistics
(clustering.py), so resampling rows of these arrays preserves within-user
structure automatically (a user's sessions are already collapsed into a
single number before this function ever sees them).
"""

from __future__ import annotations

import numpy as np

DEFAULT_SEED = 1234567  # fixed for reproducible reporting; not a security-sensitive seed
DEFAULT_N_BOOT = 10_000


def cluster_bootstrap_ci(
    v1: np.ndarray,
    v2: np.ndarray,
    stat: str = "mean",
    n_boot: int = DEFAULT_N_BOOT,
    confidence: float = 0.95,
    seed: int = DEFAULT_SEED,
) -> dict:
    """95% (by default) percentile CI for statistic(v2) - statistic(v1).

    Vectorized: draws all n_boot resamples for each arm at once rather than
    looping in Python, since this runs once per metric per segment in the
    experiment-results report.
    """
    if stat not in ("mean", "median"):
        raise ValueError("stat must be 'mean' or 'median'")
    reducer = np.mean if stat == "mean" else np.median

    rng = np.random.default_rng(seed)
    n1, n2 = len(v1), len(v2)
    if n1 == 0 or n2 == 0:
        return {"point_estimate": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"), "n_boot": n_boot, "stat": stat}

    idx1 = rng.integers(0, n1, size=(n_boot, n1))
    idx2 = rng.integers(0, n2, size=(n_boot, n2))
    resampled1 = reducer(v1[idx1], axis=1)
    resampled2 = reducer(v2[idx2], axis=1)
    diffs = resampled2 - resampled1

    alpha = 1 - confidence
    lower = float(np.percentile(diffs, 100 * alpha / 2))
    upper = float(np.percentile(diffs, 100 * (1 - alpha / 2)))
    point = float(reducer(v2) - reducer(v1))
    return {"point_estimate": point, "ci_low": lower, "ci_high": upper, "n_boot": n_boot, "stat": stat}
