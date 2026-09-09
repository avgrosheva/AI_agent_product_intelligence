"""Stage 11 task 4: deterministic representative-session selection —
pure, no database. Same input always produces the same output, and the
selection prefers (in order) the dominant failure mechanism, then the
domain's own negative outcome, then just the treatment arm."""

from __future__ import annotations

import pandas as pd

from backend.core.trajectory_config import TrajectoryConfig
from backend.investigation.evidence import select_representative_sessions

TC = TrajectoryConfig(outcome_column="outcome_label", negative_outcome_value="abandoned")


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_prefers_sessions_with_the_dominant_failure_mode():
    df = _df(
        [
            {"session_id": "s1", "agent_version": "v2", "outcome_label": "resolved", "retrieval_failure": True},
            {"session_id": "s2", "agent_version": "v2", "outcome_label": "resolved", "retrieval_failure": False},
            {"session_id": "s3", "agent_version": "v1", "outcome_label": "abandoned", "retrieval_failure": True},
        ]
    )
    result = select_representative_sessions(df, "retrieval_failure", TC)
    assert result == ["s1"]  # only the v2 row with the mechanism detected -- v1 rows are never candidates


def test_falls_back_to_negative_outcome_when_no_mechanism_detected_in_treatment():
    df = _df(
        [
            {"session_id": "s1", "agent_version": "v2", "outcome_label": "abandoned", "retrieval_failure": False},
            {"session_id": "s2", "agent_version": "v2", "outcome_label": "resolved", "retrieval_failure": False},
        ]
    )
    result = select_representative_sessions(df, "retrieval_failure", TC)
    assert result == ["s1"]


def test_falls_back_to_whole_treatment_arm_when_nothing_else_matches():
    df = _df(
        [
            {"session_id": "s2", "agent_version": "v2", "outcome_label": "resolved"},
            {"session_id": "s1", "agent_version": "v2", "outcome_label": "resolved"},
        ]
    )
    result = select_representative_sessions(df, None, TC)
    assert result == ["s1", "s2"]  # sorted, not insertion order


def test_never_selects_control_arm_sessions():
    df = _df([{"session_id": "s1", "agent_version": "v1", "outcome_label": "abandoned"}])
    result = select_representative_sessions(df, None, TC)
    assert result == []


def test_caps_at_n():
    rows = [{"session_id": f"s{i}", "agent_version": "v2", "outcome_label": "resolved"} for i in range(10)]
    result = select_representative_sessions(_df(rows), None, TC, n=3)
    assert result == ["s0", "s1", "s2"]


def test_empty_dataframe_returns_empty_list():
    assert select_representative_sessions(_df([]), None, TC) == []


def test_deterministic_across_repeated_calls():
    df = _df([{"session_id": "s2", "agent_version": "v2", "outcome_label": "resolved"}, {"session_id": "s1", "agent_version": "v2", "outcome_label": "resolved"}])
    first = select_representative_sessions(df, None, TC)
    second = select_representative_sessions(df, None, TC)
    assert first == second == ["s1", "s2"]
