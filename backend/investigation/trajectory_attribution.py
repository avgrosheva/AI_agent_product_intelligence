"""Independent trajectory reconstruction, canonicalization, and
outcome-association testing (INVESTIGATION.md SS5; Stage 2 review
requirement #5).

Reconstructs patterns from `agent_actions` from scratch every time this
runs. It does not read, import, or otherwise depend on
`has_consecutive_search` or any other Stage 2 descriptive sanity-check
column (session_level_base.sql), and it does not hard-code which pattern
"the" planted regression looks like — whatever pattern the chi-square/
Fisher scan surfaces as associated with a worse outcome in a given segment
is reported, whether or not it matches any effect this project happens to
know was planted. Findings are reported as associations, never causal
claims (Stage 2 review requirement #7).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from scipy.stats import chi2_contingency, fisher_exact

from backend.investigation.thresholds import MIN_PATTERN_SESSIONS_FOR_TEST, RARE_SEQUENCE_MIN_COUNT


def reconstruct_trajectories(agent_actions_df: pd.DataFrame) -> pd.DataFrame:
    """One row per session_id: the exact ordered action_type sequence,
    derived solely from agent_actions.sequence_index — no other input."""
    ordered = agent_actions_df.sort_values(["session_id", "sequence_index"])
    grouped = ordered.groupby("session_id")["action_type"].apply(tuple)
    return grouped.reset_index().rename(columns={"action_type": "action_sequence"})


def _structural_features(seq: tuple[str, ...]) -> tuple[bool, int, bool, int]:
    has_clarify = "clarify" in seq
    num_search_repeats = sum(1 for a, b in zip(seq, seq[1:]) if a == "search" and b == "search")
    ends_in_abandon = bool(seq) and seq[-1] == "abandon_flow"
    num_actions = len(seq)
    return (has_clarify, num_search_repeats, ends_in_abandon, num_actions)


def canonicalize_patterns(trajectories_df: pd.DataFrame, min_count: int = RARE_SEQUENCE_MIN_COUNT) -> pd.DataFrame:
    """Sequences occurring at least `min_count` times within the scope
    passed in keep their literal identity; rarer ones collapse to a
    structural-feature key (INVESTIGATION.md SS5: has_clarify,
    num_search_repeats, ends_in_abandon, num_actions) so a long tail of
    near-duplicate exact sequences doesn't fragment the analysis."""
    counts = trajectories_df["action_sequence"].value_counts()

    def pattern_for(seq: tuple[str, ...]) -> str:
        if counts[seq] >= min_count:
            return "exact:" + ">".join(seq)
        has_clarify, num_search_repeats, ends_in_abandon, num_actions = _structural_features(seq)
        return f"structural:clarify={has_clarify},search_repeats={num_search_repeats},ends_abandon={ends_in_abandon},n_actions={num_actions}"

    out = trajectories_df.copy()
    out["pattern"] = out["action_sequence"].apply(pattern_for)
    return out


@dataclass
class PatternAssociation:
    pattern: str
    n_sessions: int
    pattern_outcome_rate: float
    baseline_outcome_rate: float
    test_name: str
    p_value: float
    bh_significant: bool = False


def test_pattern_outcome_association(
    df_with_patterns: pd.DataFrame,
    outcome_col: str = "abandoned",
    min_sessions: int = MIN_PATTERN_SESSIONS_FOR_TEST,
) -> list[PatternAssociation]:
    """For each pattern with enough sessions, test whether its outcome rate
    differs from the scope's overall rate. Returns raw (uncorrected)
    p-values — the caller (pipeline.py) pools these across every segment's
    trajectory tests in one Investigation run and applies a single BH pass,
    per INVESTIGATION.md SS5's "again BH-corrected within the run.\""""
    n_total = len(df_with_patterns)
    total_outcome = int(df_with_patterns[outcome_col].sum())
    results: list[PatternAssociation] = []

    for pattern, group in df_with_patterns.groupby("pattern"):
        n_pattern = len(group)
        if n_pattern < min_sessions:
            continue
        pattern_outcome = int(group[outcome_col].sum())
        rest_n = n_total - n_pattern
        rest_outcome = total_outcome - pattern_outcome
        table = [[pattern_outcome, n_pattern - pattern_outcome], [rest_outcome, rest_n - rest_outcome]]

        if min(min(row) for row in table) < 5:
            _, p_value = fisher_exact(table)
            test_name = "fisher_exact"
        else:
            _, p_value, _, _ = chi2_contingency(table)
            test_name = "chi_square"

        results.append(
            PatternAssociation(
                pattern=pattern,
                n_sessions=n_pattern,
                pattern_outcome_rate=pattern_outcome / n_pattern,
                baseline_outcome_rate=total_outcome / n_total if n_total else 0.0,
                test_name=test_name,
                p_value=float(p_value),
            )
        )
    return results
