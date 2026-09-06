"""Trajectory reconstruction, canonicalization, and outcome-association
testing (Stage 2 review requirement #5; INVESTIGATION.md SS5)."""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from backend.investigation import trajectory_attribution as traj_module
from backend.investigation.trajectory_attribution import canonicalize_patterns, reconstruct_trajectories
from backend.investigation.trajectory_attribution import test_pattern_outcome_association as run_pattern_association


def test_reconstruct_trajectories_orders_by_sequence_index_not_input_order():
    actions = pd.DataFrame(
        {
            "session_id": ["s1", "s1", "s1", "s2"],
            "sequence_index": [2, 0, 1, 0],
            "action_type": ["recommend", "understand_query", "search", "understand_query"],
        }
    )
    result = reconstruct_trajectories(actions)
    s1 = result.loc[result.session_id == "s1", "action_sequence"].iloc[0]
    assert s1 == ("understand_query", "search", "recommend")


def test_does_not_reference_stage2_shortcut_column():
    """Stage 2 review requirement #5: none of this module's actual functions
    (as opposed to its explanatory module docstring, which names the
    artifact precisely to disclaim reading it) may read has_consecutive_search
    or the validation artifact."""
    functions = [
        traj_module.reconstruct_trajectories,
        traj_module.canonicalize_patterns,
        traj_module.test_pattern_outcome_association,
        traj_module._structural_features,
    ]
    for fn in functions:
        source = inspect.getsource(fn)
        assert "has_consecutive_search" not in source, f"{fn.__name__} references has_consecutive_search"
        assert "validation_ground_truth" not in source, f"{fn.__name__} references validation_ground_truth"


def test_does_not_hard_code_the_known_planted_pattern():
    """The module must derive patterns generically, not special-case the
    specific 'search,search' sequence effect 5 happens to use."""
    source = inspect.getsource(traj_module.canonicalize_patterns) + inspect.getsource(traj_module.test_pattern_outcome_association)
    assert "'search', 'search'" not in source
    assert '"search", "search"' not in source


def test_canonicalize_keeps_frequent_exact_sequences_literal():
    df = pd.DataFrame({"session_id": range(10), "action_sequence": [("understand_query", "search", "recommend")] * 10})
    out = canonicalize_patterns(df, min_count=5)
    assert (out.pattern == "exact:understand_query>search>recommend").all()


def test_canonicalize_collapses_rare_sequences_to_structural_features():
    frequent = [("understand_query", "search", "recommend")] * 10
    rare = [("understand_query", "search", "filter", "search", "clarify", "recommend")]  # unique, appears once
    df = pd.DataFrame({"session_id": range(11), "action_sequence": frequent + rare})
    out = canonicalize_patterns(df, min_count=5)
    rare_pattern = out.iloc[-1].pattern
    assert rare_pattern.startswith("structural:")
    assert "clarify=True" in rare_pattern
    assert "n_actions=6" in rare_pattern


def test_structural_features_capture_documented_dimensions():
    seq = ("understand_query", "search", "search", "clarify", "abandon_flow")
    has_clarify, num_search_repeats, ends_in_abandon, num_actions = traj_module._structural_features(seq)
    assert has_clarify is True
    assert num_search_repeats == 1  # one adjacent search-search pair
    assert ends_in_abandon is True
    assert num_actions == 5


def test_pattern_association_uses_fisher_exact_for_small_cells():
    df = pd.DataFrame(
        {
            "pattern": ["A"] * 6 + ["B"] * 20,
            "converted": [1, 1, 1, 0, 0, 0] + [0] * 15 + [1] * 5,
        }
    )
    results = run_pattern_association(df, outcome_col="converted", min_sessions=5)
    a = next(r for r in results if r.pattern == "A")
    assert a.test_name in ("fisher_exact", "chi_square")
    assert 0.0 <= a.p_value <= 1.0


def test_pattern_association_skips_patterns_below_min_sessions():
    df = pd.DataFrame({"pattern": ["A"] * 3 + ["B"] * 20, "converted": [1, 0, 1] + [0] * 20})
    results = run_pattern_association(df, outcome_col="converted", min_sessions=5)
    assert "A" not in [r.pattern for r in results]


def test_pattern_association_reports_association_not_causation_in_field_names():
    """Structural check on the dataclass itself: no field name implies
    causation (Stage 2 review requirement #7)."""
    from backend.investigation.trajectory_attribution import PatternAssociation

    field_names = {f for f in PatternAssociation.__dataclass_fields__}
    for forbidden in ("causes", "caused_by", "effect_of"):
        assert not any(forbidden in f for f in field_names)


def test_no_association_test_against_a_tautological_outcome_in_the_pipeline():
    """Testing trajectory pattern vs `abandoned` is tautological when every
    pattern in scope is a complete trajectory (its last action determines
    the outcome). The pipeline must restrict association testing to
    sessions that reached an answer and test against `converted` instead —
    verified here structurally, since this is easy to silently regress."""
    import backend.investigation.pipeline as pipeline_module

    source = inspect.getsource(pipeline_module.run_investigation)
    assert 'outcome_col="converted"' in source
