"""Stage 11 task 4: deterministic representative-session selection for
one Investigation finding. Reproducible (same input -> same output,
never randomized) and explainable (the policy below is the whole
algorithm — no scoring model, no fabricated ranking). Pure function: it
takes the finding's own already-computed segment dataframe (from
backend.investigation.pipeline.run_investigation, which has this data in
hand already) and returns a small ordered list of session ids.
"""

from __future__ import annotations

import pandas as pd

from backend.core.trajectory_config import TrajectoryConfig

DEFAULT_SAMPLE_SIZE = 3


def select_representative_sessions(
    seg_df: pd.DataFrame,
    dominant_failure_mode: str | None,
    trajectory_config: TrajectoryConfig,
    n: int = DEFAULT_SAMPLE_SIZE,
) -> list[str]:
    """Selection policy, in priority order (each step only used if the
    previous one found nothing):
    1. Treatment-arm ("v2") sessions in this segment for which the
       finding's own dominant failure mechanism was detected=true.
    2. Treatment-arm sessions whose outcome equals this domain's own
       configured negative-outcome value (backend.core.trajectory_config).
    3. Every treatment-arm session in this segment.
    Session ids are sorted (not insertion order, not randomness) before
    taking the first `n` — the same segment always yields the same
    representative sessions."""
    if seg_df.empty or "agent_version" not in seg_df.columns or "session_id" not in seg_df.columns:
        return []

    treatment = seg_df[seg_df["agent_version"] == "v2"]
    if treatment.empty:
        return []

    candidates = pd.DataFrame()
    if dominant_failure_mode and dominant_failure_mode in treatment.columns:
        candidates = treatment[treatment[dominant_failure_mode] == True]  # noqa: E712
    if candidates.empty and trajectory_config.outcome_column in treatment.columns:
        candidates = treatment[treatment[trajectory_config.outcome_column] == trajectory_config.negative_outcome_value]
    if candidates.empty:
        candidates = treatment

    return sorted({str(sid) for sid in candidates["session_id"]})[:n]
