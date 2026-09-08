"""Excess-abandonment decomposition edge cases (Stage 2 review requirement
#8): zero total excess, negative mode-level excess, shares above 100% with
offsetting modes, shares that don't sum neatly to 100%, segments where
treatment improves abandonment, and — hybrid multi-label redesign —
overlapping mechanisms whose shares are not expected to sum to anything in
particular. Nothing here may be silently clamped or renormalized.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.investigation.failure_attribution import compute_failure_attribution
from backend.investigation.thresholds import MIN_EXCESS_ABANDONMENT_COUNT


def _rows(agent_version: str, n: int, n_abandoned: int, mechanisms_for_abandoned: list[set[str]], mechanisms_for_rest: set[str] = frozenset()) -> list[dict]:
    """One row per session with a boolean column per mechanism named in
    any of the sets passed — a session's column is True iff that mechanism
    is in its own set. Multiple mechanisms per session (multi-label
    overlap) are expressed simply by putting more than one name in a set."""
    assert len(mechanisms_for_abandoned) == n_abandoned
    all_mechanisms = set(mechanisms_for_rest)
    for mechs in mechanisms_for_abandoned:
        all_mechanisms |= mechs

    def _row(abandoned: int, mechs: set[str]) -> dict:
        r = {"agent_version": agent_version, "abandoned": abandoned}
        for m in all_mechanisms:
            r[m] = m in mechs
        return r

    rows = [_row(1, mechs) for mechs in mechanisms_for_abandoned]
    rows += [_row(0, mechanisms_for_rest) for _ in range(n - n_abandoned)]
    return rows


def _frame(*row_groups: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame([r for group in row_groups for r in group])
    mechanism_cols = [c for c in df.columns if c not in ("agent_version", "abandoned")]
    df[mechanism_cols] = df[mechanism_cols].fillna(False)
    return df


def test_zero_total_excess_abandonment_reports_no_shares():
    """Identical abandonment rates in both arms -> E=0 -> not reportable,
    every mechanism's share is None (never silently set to 0 or 100%)."""
    df = _frame(
        _rows("v1", 10, 2, [{"unnecessary_clarification"}, set()]),
        _rows("v2", 10, 2, [{"unnecessary_clarification"}, set()]),
    )
    result = compute_failure_attribution(df, mechanisms=("unnecessary_clarification",))
    assert result.total_excess_abandonment == pytest.approx(0.0)
    assert result.reportable is False
    assert all(m.share_of_excess_abandonment is None for m in result.per_mode)


def test_segment_where_treatment_improves_abandonment_reports_negative_excess():
    """v2 abandons less than v1 -> E < 0, reported as-is, not clamped to 0."""
    df = _frame(
        _rows("v1", 20, 10, [set()] * 10),
        _rows("v2", 20, 5, [set()] * 5),
    )
    result = compute_failure_attribution(df, mechanisms=())
    assert result.total_excess_abandonment == pytest.approx(-5.0)
    assert result.reportable is True  # |−5| >= MIN_EXCESS_ABANDONMENT_COUNT (5)
    assert result.abandonment_rate_v2 < result.abandonment_rate_v1


def test_negative_mode_level_excess_and_share_above_100pct_not_clamped():
    """Constructed so one mechanism's excess exceeds the segment total
    (share > 1) while another's excess is negative (share < 0) — both
    reported verbatim. Since modeA/modeB are mutually exclusive in this
    fabricated data (a degenerate, single-label-like case of the general
    multi-label function), shares still sum to exactly 1.0 here — that is
    a property of THIS data, not a general guarantee the function enforces
    (see the overlap test below, where it does not hold)."""
    df = _frame(
        _rows("v1", 20, 4, [{"modeA"}, {"modeB"}, {"modeB"}, {"modeB"}]),
        _rows("v2", 20, 10, [{"modeA"}] * 9 + [{"modeB"}]),
    )
    result = compute_failure_attribution(df, mechanisms=("modeA", "modeB"))
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
    assert total_share == pytest.approx(1.0), "shares happen to sum to 1.0 when mechanisms are mutually exclusive in the data"


def test_overlapping_mechanisms_do_not_sum_to_100pct():
    """Hybrid multi-label redesign: a session can have multiple mechanisms
    detected simultaneously. Shares must NOT be forced/renormalized to sum
    to any particular total when mechanisms overlap."""
    df = _frame(
        _rows("v1", 20, 2, [set(), set()]),
        _rows("v2", 20, 8, [{"modeA"}, {"modeA"}, {"modeA", "modeB"}, {"modeA", "modeB"}, {"modeB"}, {"modeB"}, set(), set()]),
    )
    result = compute_failure_attribution(df, mechanisms=("modeA", "modeB"))
    assert result.reportable is True
    total_share = sum(m.share_of_excess_abandonment for m in result.per_mode if m.share_of_excess_abandonment is not None)
    assert total_share != pytest.approx(1.0), "overlapping mechanisms should not sum to a clean 100%"


def test_shares_do_not_sum_neatly_to_100pct_when_a_mode_is_excluded_from_taxonomy():
    """If the mechanism tuple passed in doesn't cover every mechanism
    actually present in the data (e.g. an unexpected/unlabeled column),
    the decomposition must NOT be silently renormalized to force a 100%
    total — the gap is left visible."""
    df = _frame(
        _rows("v1", 20, 2, [{"modeA"}, set()]),
        _rows("v2", 20, 8, [{"modeA"}, {"modeA"}, {"modeA"}, {"unmodeled_mode"}, {"unmodeled_mode"}, {"unmodeled_mode"}, set(), set()]),
    )
    # mechanisms passed to the function omits "unmodeled_mode" on purpose
    result = compute_failure_attribution(df, mechanisms=("modeA",))
    assert result.reportable is True
    total_share = sum(m.share_of_excess_abandonment for m in result.per_mode if m.share_of_excess_abandonment is not None)
    assert total_share != pytest.approx(1.0), "excluding a real mechanism should leave a visible gap, not be papered over"


def test_share_not_computed_below_min_excess_threshold_even_if_technically_divisible():
    """A segment with a tiny but nonzero E should not report shares — the
    ratio would be numerically valid but statistically meaningless."""
    df = _frame(
        _rows("v1", 100, 10, [set()] * 10),
        _rows("v2", 100, 11, [{"unnecessary_clarification"}] + [set()] * 10),
    )
    result = compute_failure_attribution(df, mechanisms=("unnecessary_clarification",))
    assert abs(result.total_excess_abandonment) < MIN_EXCESS_ABANDONMENT_COUNT
    assert result.reportable is False
    assert all(m.share_of_excess_abandonment is None for m in result.per_mode)


def test_raw_share_of_failures_uses_all_v2_sessions_not_only_abandoned():
    """The naive 'share of failures' framing (context alongside the excess
    share) counts every v2 session with the mechanism detected, not only
    abandoned ones, against a denominator of "any mechanism detected"
    (mechanisms are independent now, so there is no single 'none' column
    to exclude by name — a session with nothing detected simply doesn't
    count toward the denominator)."""
    df = _frame(
        _rows("v1", 10, 2, [{"modeA"}, set()]),
        [{"agent_version": "v2", "abandoned": 0, "modeA": True}] * 3
        + [{"agent_version": "v2", "abandoned": 1, "modeA": True}] * 2
        + [{"agent_version": "v2", "abandoned": 0, "modeA": False}] * 5,
    )
    result = compute_failure_attribution(df, mechanisms=("modeA",))
    by_mode = {m.failure_mode: m for m in result.per_mode}
    # 5 modeA-detected v2 sessions (3 non-abandoned + 2 abandoned) out of 5 total any-mechanism-detected v2 sessions
    assert by_mode["modeA"].raw_share_of_v2_failures == pytest.approx(1.0)
