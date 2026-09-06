"""Stage 2 manual verification of the five planted effects using ONLY
observable application data (Stage 1 review requirements). This is
distinct from — and must not reuse — tests/test_planted_effects.py, which
Stage 1 review explicitly scoped as a generator sanity check, not
production inference methodology.
"""

from __future__ import annotations

import pytest

from backend.analytics.effects_verification import (
    verify_android_latency_effect,
    verify_named_effects,
    verify_tool_selection_effect,
)
from backend.analytics.sql_runner import run_sql_file


@pytest.fixture(scope="module")
def base_df(db_engine):
    return run_sql_file(db_engine, "session_level_base.sql")


def test_does_not_import_validation_ground_truth():
    """Structural guard: none of this module's actual functions (as opposed
    to its explanatory module docstring, which mentions the artifact by
    name precisely to disclaim reading it) may reference the isolated
    validation artifact (DATA_MODEL.md SS8)."""
    import inspect

    import backend.analytics.effects_verification as mod

    functions = [mod.verify_named_effects, mod.verify_tool_selection_effect, mod.verify_android_latency_effect]
    for fn in functions:
        source = inspect.getsource(fn)
        assert "validation_ground_truth" not in source, f"{fn.__name__} references validation_ground_truth"
        assert "ground_truth" not in source, f"{fn.__name__} references ground_truth"


def test_all_named_effect_checks_show_expected_direction(base_df):
    report = verify_named_effects(base_df)
    mismatches = report[~report.direction_matches]
    assert mismatches.empty, f"direction mismatches found:\n{mismatches[['effect', 'metric', 'expected_direction', 'observed_direction']]}"


def test_overclarify_and_monitor_effects_are_significant_at_dev_scale(base_df):
    """The two strongest planted effects should already be detectable even
    at dev scale; the other three are allowed to be underpowered
    (Stage 1 review requirement #9)."""
    report = verify_named_effects(base_df)
    overclarify = report[report.effect == "overclarify_v2"]
    assert (overclarify.verdict == "significant").all()

    monitor_satisfaction = report[(report.effect == "monitor_constraint_regression_v2") & (report.metric == "constraint_satisfaction_rate")]
    assert (monitor_satisfaction.verdict == "significant").all()


def test_android_latency_effect_is_significant_and_isolated(base_df):
    result = verify_android_latency_effect(base_df)
    assert result["verdict"] == "significant"
    assert result["mean_latency_ms_v2"] > result["mean_latency_ms_v1"]
    assert result["android_gap_clearly_larger"] is True


def test_tool_selection_effect_direction_correct_though_possibly_underpowered(base_df):
    """Stage 1 review requirement #9: correct direction with wide CIs is an
    acceptable dev-scale outcome; this must not be tuned to force
    significance."""
    result = verify_tool_selection_effect(base_df)
    assert result["observed_direction"] == "v2 lower"


def test_every_effect_check_reports_sample_sizes(base_df):
    report = verify_named_effects(base_df)
    assert (report.n_users_v1 > 0).all()
    assert (report.n_users_v2 > 0).all()
