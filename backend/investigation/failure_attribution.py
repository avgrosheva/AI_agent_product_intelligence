"""Excess-abandonment decomposition by failure mode (INVESTIGATION.md SS4,
exactly as revised). Operates on session-level counts within a segment —
this is a decomposition of an already-observed rate difference, not itself
a significance test, so it does not go through the cluster-level machinery
in backend/analytics/stats/.

Terminology, enforced here and in every caller: this module computes
"share of excess abandonment ASSOCIATED WITH failure mode X," never "share
ATTRIBUTABLE TO X" or "caused by X" (Stage 2 review requirement #7). A
failure_labels row is a classifier output correlated with abandonment, not
the result of a controlled intervention on that specific mechanism.

Reads only the already-loaded application `failure_labels` table (source=
'llm_classifier') via the caller-supplied DataFrame — never
validation_ground_truth.parquet (Stage 2 review requirement #4).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backend.investigation.thresholds import MIN_EXCESS_ABANDONMENT_COUNT


@dataclass
class ModeExcess:
    failure_mode: str
    excess_count: float                  # E_X(segment) — can be negative
    share_of_excess_abandonment: float | None  # E_X / E, or None if |E| too small to report
    raw_share_of_v2_failures: float | None      # count(mode=X, v2) / count(mode != 'none', v2) — the naive/common-but-not-causal framing


@dataclass
class FailureAttributionResult:
    segment_label: str
    n_v1: int
    n_v2: int
    abandonment_rate_v1: float
    abandonment_rate_v2: float
    total_excess_abandonment: float      # E(segment) — can be negative (v2 improves) or ~0
    per_mode: list[ModeExcess]
    reportable: bool                     # False if |E(segment)| < MIN_EXCESS_ABANDONMENT_COUNT


def compute_failure_attribution(
    segment_sessions: pd.DataFrame,
    taxonomy: tuple[str, ...],
    min_excess_count: float = MIN_EXCESS_ABANDONMENT_COUNT,
) -> FailureAttributionResult:
    """`segment_sessions` must already be filtered to the segment of
    interest and merged with failure_labels, with columns:
    agent_version, abandoned (0/1), failure_mode (one of `taxonomy`).
    """
    v1 = segment_sessions[segment_sessions.agent_version == "v1"]
    v2 = segment_sessions[segment_sessions.agent_version == "v2"]
    n_v1, n_v2 = len(v1), len(v2)

    aband_rate_v1 = float(v1["abandoned"].mean()) if n_v1 else 0.0
    aband_rate_v2 = float(v2["abandoned"].mean()) if n_v2 else 0.0
    total_excess = n_v2 * (aband_rate_v2 - aband_rate_v1)
    reportable = abs(total_excess) >= min_excess_count

    v2_failure_denominator = int((v2["failure_mode"] != "none").sum())

    per_mode: list[ModeExcess] = []
    for mode in taxonomy:
        count_abandoned_mode_v1 = int(((v1["abandoned"] == 1) & (v1["failure_mode"] == mode)).sum())
        rate_v1_with_mode = count_abandoned_mode_v1 / n_v1 if n_v1 else 0.0
        count_abandoned_mode_v2 = int(((v2["abandoned"] == 1) & (v2["failure_mode"] == mode)).sum())
        rate_v2_with_mode = count_abandoned_mode_v2 / n_v2 if n_v2 else 0.0

        excess_mode = n_v2 * (rate_v2_with_mode - rate_v1_with_mode)
        # Deliberately NOT clamped or renormalized (Stage 2 review requirement
        # #8): can be negative, and shares can exceed 1.0 in magnitude when
        # another mode offsets it — both are reported as-is.
        share = (excess_mode / total_excess) if reportable else None

        raw_share = None
        if mode != "none" and v2_failure_denominator > 0:
            count_mode_v2 = int((v2["failure_mode"] == mode).sum())
            raw_share = count_mode_v2 / v2_failure_denominator

        per_mode.append(
            ModeExcess(
                failure_mode=mode,
                excess_count=excess_mode,
                share_of_excess_abandonment=share,
                raw_share_of_v2_failures=raw_share,
            )
        )

    return FailureAttributionResult(
        segment_label="",  # set by caller
        n_v1=n_v1,
        n_v2=n_v2,
        abandonment_rate_v1=aband_rate_v1,
        abandonment_rate_v2=aband_rate_v2,
        total_excess_abandonment=total_excess,
        per_mode=per_mode,
        reportable=reportable,
    )
