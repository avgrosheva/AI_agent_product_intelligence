"""Reduce session-level observations to one row per user.

STATISTICS.md SS2: the experiment randomizes users, not sessions, so every
inferential comparison in this package operates on a per-user cluster
statistic (a user's own rate or mean across their sessions in the segment
being analyzed), never on raw pooled session rows. Session-level values
remain useful for descriptive reporting (backend/analytics/sql/) but are
never the input to a significance test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def user_cluster_stat(
    sessions: pd.DataFrame,
    value_col: str,
    user_col: str = "user_id",
    version_col: str = "agent_version",
) -> pd.DataFrame:
    """One row per (user, version) with that user's mean of `value_col`
    across their sessions in `sessions`. A user has exactly one version by
    construction (DATA_MODEL.md SS3.4), so grouping by both columns is
    equivalent to grouping by user alone but keeps the version label
    attached for the caller.
    """
    return (
        sessions.groupby([user_col, version_col], observed=True)[value_col]
        .mean()
        .reset_index()
    )


def cluster_arrays(
    sessions: pd.DataFrame,
    value_col: str,
    user_col: str = "user_id",
    version_col: str = "agent_version",
) -> dict[str, np.ndarray]:
    """{'v1': array of per-user cluster means, 'v2': array of per-user cluster means}."""
    per_user = user_cluster_stat(sessions, value_col, user_col, version_col)
    return {
        version: group[value_col].to_numpy()
        for version, group in per_user.groupby(version_col, observed=True)
    }


def assert_single_version_per_user(sessions: pd.DataFrame, user_col: str = "user_id", version_col: str = "agent_version") -> None:
    """Defensive guard used by experiment_results.py before running any
    test: if this ever fails, the cluster-level machinery's core assumption
    (one version per user) has been violated upstream."""
    counts = sessions.groupby(user_col)[version_col].nunique()
    offenders = counts[counts > 1]
    if len(offenders) > 0:
        raise ValueError(f"{len(offenders)} users have more than one agent_version in this data slice")
