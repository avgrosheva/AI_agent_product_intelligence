"""Excess-abandonment decomposition edge cases (Stage 2 review requirement
#8): zero total excess, negative mode-level excess, shares above 100% with
offsetting modes, shares that don't sum neatly to 100%, and segments where
treatment improves abandonment. Nothing here may be silently clamped or
renormalized.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.investigation.failure_attribution import compute_failure_attribution
from backend.investigation.thresholds import MIN_EXCESS_ABANDONMENT_COUNT


def _rows(agent_version: str, n: int, n_abandoned: int, mode_for_abandoned: list[str], mode_for_rest: str = "none") -> list[dict]:
    assert len(mode_for_abandoned) == n_abandoned
    rows = [{"agent_version": agent_version, "abandoned": 1, "failure_mode": m} for m in mode_for_abandoned]
    rows += [{"agent_version": agent_version, "abandoned": 0, "failure_mode": mode_for_rest} for _ in range(n - n_abandoned)]
    return rows


def test_zero_total_excess_abandonment_reports_no_shares():
    """Identical abandonment rates in both arms -> E=0 -> not reportable,
    every mode's share is None (never silently set to 0 or 100%)."""
    df = pd.DataFrame(
        _rows("v1", 10, 2, ["unnecessary_clarification", "none"])
        + _rows("v2", 10, 2, ["unnecessary_clarification", "none"])
    )
    result = compute_failure_attribution(df, taxonomy=("unnecessary_clarification", "none"))
    assert result.total_excess_abandonment == pytest.approx(0.0)
    assert result.reportable is False
    assert all(m.share_of_excess_abandonment is None for m in result.per_mode)


def test_segment_where_treatment_improves_abandonment_reports_negative_excess():
    """v2 abandons less than v1 -> E < 0, reported as-is, not clamped to 0."""
    df = pd.DataFrame(
        _rows("v1", 20, 10, ["none"] * 10)
        + _rows("v2", 20, 5, ["none"] * 5)
    )
    result = compute_failure_attribution(df, taxonomy=("none",))
    assert result.total_excess_abandonment == pytest.approx(-5.0)
    assert result.reportable is True  # |−5| >= MIN_EXCESS_ABANDONMENT_COUNT (5)
    assert result.abandonment_rate_v2 < result.abandonment_rate_v1


def test_negative_mode_level_excess_and_share_above_100pct_not_clamped():
    """Constructed so one mode's excess exceeds the segment total (share > 1)
    while another mode's excess is negative (share < 0) — both reported
    verbatim, and they still sum to exactly 1.0 (partition identity)."""
    df = pd.DataFrame(
        _rows("v1", 20, 4, ["modeA", "modeB", "modeB", "modeB"])
        + _rows("v2", 20, 10, ["modeA"] * 9 + ["modeB"])
    )
    result = compute_failure_attribution(df, taxonomy=("modeA", "modeB", "none"))
    assert result.total_excess_abandonment == pytest.approx(6.0)
    assert result.reportable is True

    by_mode = {m.failure_mode: m for m in result.per_mode}
    assert by_mode["modeA"].excess_count == pytest.approx(8.0)
    assert by_mode["modeA"].share_of_excess_abandonment == pytest.approx(8 / 6)
    assert by_mode["modeA"].share_of_excess_abandonment > 1.0, "share above 100% must not be clamped"

    assert by_mode["modeB"].excess_count == pytest.approx(-2.0)
    assert by_mode["modeB"].share_of_excess_abandonment == pytest.approx(-2 / 6)
    assert by_mode["modeB"].share_of_excess_abandonment < 0.0, "negative share must not be clamped to 0"

    total_share = sum(m.share_of_excess_abandonment for m in result.per_mode)
    assert total_share == pytest.approx(1.0), "shares must still partition exactly when every mode is included"


def test_shares_do_not_sum_neatly_to_100pct_when_a_mode_is_excluded_from_taxonomy():
    """If the taxonomy passed in doesn't cover every mode actually present
    in the data (e.g. an unexpected/unlabeled value), the decomposition
    must NOT be silently renormalized to force a 100% total — the gap is
    left visible."""
    df = pd.DataFrame(
        _rows("v1", 20, 2, ["modeA", "none"])
        + _rows("v2", 20, 8, ["modeA", "modeA", "modeA", "unmodeled_mode", "unmodeled_mode", "unmodeled_mode", "none", "none"])
    )
    # taxonomy passed to the function omits "unmodeled_mode" on purpose
    result = compute_failure_attribution(df, taxonomy=("modeA", "none"))
    assert result.reportable is True
    total_share = sum(m.share_of_excess_abandonment for m in result.per_mode if m.share_of_excess_abandonment is not None)
    assert total_share != pytest.approx(1.0), "excluding a real mode from the taxonomy should leave a visible gap, not be papered over"


def test_share_not_computed_below_min_excess_threshold_even_if_technically_divisible():
    """A segment with a tiny but nonzero E should not report shares — the
    ratio would be numerically valid but statistically meaningless."""
    df = pd.DataFrame(
        _rows("v1", 100, 10, ["none"] * 10)
        + _rows("v2", 100, 11, ["unnecessary_clarification"] + ["none"] * 10)
    )
    result = compute_failure_attribution(df, taxonomy=("unnecessary_clarification", "none"))
    assert abs(result.total_excess_abandonment) < MIN_EXCESS_ABANDONMENT_COUNT
    assert result.reportable is False
    assert all(m.share_of_excess_abandonment is None for m in result.per_mode)


def test_raw_share_of_failures_uses_all_v2_sessions_not_only_abandoned():
    """The naive 'share of failures' framing (context alongside the excess
    share) counts every v2 session labeled X, not only abandoned ones."""
    df = pd.DataFrame(
        _rows("v1", 10, 2, ["modeA", "none"])
        + [{"agent_version": "v2", "abandoned": 0, "failure_mode": "modeA"} for _ in range(3)]
        + [{"agent_version": "v2", "abandoned": 1, "failure_mode": "modeA"} for _ in range(2)]
        + [{"agent_version": "v2", "abandoned": 0, "failure_mode": "none"} for _ in range(5)]
    )
    result = compute_failure_attribution(df, taxonomy=("modeA", "none"))
    by_mode = {m.failure_mode: m for m in result.per_mode}
    # 5 modeA-labeled v2 sessions (3 non-abandoned + 2 abandoned) out of 5 total non-'none' v2 sessions
    assert by_mode["modeA"].raw_share_of_v2_failures == pytest.approx(1.0)
    assert by_mode["none"].raw_share_of_v2_failures is None, "'none' is excluded from the failures denominator/numerator by definition"
