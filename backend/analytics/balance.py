"""Covariate balance report for the main pre-treatment variables
(Stage 1 review requirement #4; methodology corrected after Stage 2 review).

Policy, stated explicitly because it is easy to get wrong: this module
never rebalances or reweights anything. Under a correctly randomized
finite sample, some imbalance between arms is expected sampling noise, not
evidence of a broken randomization — Stage 1's own review of the hash
function confirmed it converges to 50/50 at scale (docs/PRD.md methodology
notes). This report exists to *detect* a broken randomization (e.g. a
pre-treatment field that was accidentally computed from agent_version), not
to correct ordinary noise.

Unit of analysis, corrected: the experiment is randomized at the USER
level, so a significance test (chi-square or otherwise) on pooled SESSIONS
would treat correlated, non-independent observations as independent —
exactly the pseudoreplication problem STATISTICS.md SS2 exists to avoid,
and this report must not reintroduce it just because it isn't computing a
product-decision metric. Two corrected regimes:

- Session-varying pre-treatment covariates (requested_category,
  constraint_count_bucket, platform, device_tier) are assigned per session,
  independently of any fixed user attribute, so a per-user reduction has no
  natural single "user value" to reduce to. Per the Stage 2 review's
  explicit preference for the simpler, defensible option: these are
  reported purely DESCRIPTIVELY (proportions per arm + standardized mean
  difference, a.k.a. SMD, per category) with NO significance test and NO
  p-value. SMD is the standard covariate-balance diagnostic in the
  matching/causal-inference literature precisely because it describes
  imbalance magnitude without requiring (and risking misusing) a
  hypothesis test; conventionally |SMD| < 0.1 is considered well balanced.
- Fixed user attributes (persona, locale — the generator never varies
  locale across a user's sessions) are checked one row per user. Here a
  chi-square test is legitimate (each row is one independent user) and is
  kept.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

SESSION_LEVEL_DIMENSIONS = ["requested_category", "constraint_count_bucket", "platform", "device_tier"]
USER_LEVEL_DIMENSIONS = ["persona", "locale"]

SMD_WELL_BALANCED_THRESHOLD = 0.1


def _standardized_mean_diff(p1: float, p2: float) -> float:
    """SMD for a binary indicator (one category vs. the rest), comparing
    two proportions with a pooled-variance denominator. Undefined (0) only
    in the degenerate case where both proportions are 0 or both are 1."""
    pooled_var = (p1 * (1 - p1) + p2 * (1 - p2)) / 2
    if pooled_var == 0:
        return 0.0
    return (p1 - p2) / np.sqrt(pooled_var)


def _descriptive_balance_row(dimension: str, counts: pd.DataFrame) -> dict:
    """No significance test — proportions and SMD only. Used for
    session-varying covariates (see module docstring)."""
    props = counts.div(counts.sum(axis=0), axis=1)
    smds = {value: _standardized_mean_diff(props.loc[value, "v1"], props.loc[value, "v2"]) for value in props.index}
    return {
        "dimension": dimension,
        "n_v1": int(counts["v1"].sum()),
        "n_v2": int(counts["v2"].sum()),
        "max_abs_pct_diff": float((props["v1"] - props["v2"]).abs().max()),
        "max_abs_smd": float(max(abs(v) for v in smds.values())),
        "well_balanced": bool(max(abs(v) for v in smds.values()) < SMD_WELL_BALANCED_THRESHOLD),
        "chi2_statistic": None,
        "dof": None,
        "p_value": None,
        "method": "descriptive (proportions + SMD; no significance test - sessions are clustered within users)",
    }


def _inferential_balance_row(dimension: str, counts: pd.DataFrame) -> dict:
    """Chi-square test is valid here: one row per independent user."""
    row = _descriptive_balance_row(dimension, counts)
    chi2, p_value, dof, _ = chi2_contingency(counts)
    row.update(
        {
            "chi2_statistic": float(chi2),
            "dof": int(dof),
            "p_value": float(p_value),
            "method": "chi-square (valid: one row per independent user)",
        }
    )
    return row


def covariate_balance_report(session_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dim in SESSION_LEVEL_DIMENSIONS:
        counts = pd.crosstab(session_df[dim], session_df["agent_version"])
        rows.append({**_descriptive_balance_row(dim, counts), "unit": "session"})

    per_user = session_df.groupby("user_id").agg(
        agent_version=("agent_version", "first"),
        **{dim: (dim, "first") for dim in USER_LEVEL_DIMENSIONS},
    )
    for dim in USER_LEVEL_DIMENSIONS:
        counts = pd.crosstab(per_user[dim], per_user["agent_version"])
        rows.append({**_inferential_balance_row(dim, counts), "unit": "user"})

    return pd.DataFrame(rows)


def assignment_integrity_checks(session_df: pd.DataFrame) -> dict:
    """Stage 1 review requirement #4: stable user-level assignment, no user
    in both arms, plus a treatment-balance sanity range (not a rebalancing
    trigger — see module docstring)."""
    per_user_versions = session_df.groupby("user_id")["agent_version"].nunique()
    users_in_both_arms = int((per_user_versions > 1).sum())

    per_user = session_df.groupby("user_id")["agent_version"].first()
    n_users = len(per_user)
    share_v2 = float((per_user == "v2").mean())

    return {
        "n_users": n_users,
        "users_in_both_arms": users_in_both_arms,
        "stable_assignment": users_in_both_arms == 0,
        "share_v2": share_v2,
        "balance_within_plausible_range": 0.35 < share_v2 < 0.65,
    }
