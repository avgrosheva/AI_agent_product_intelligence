"""Ground-truth isolation must be structural, not conventional
(DATA_MODEL.md SS1, SS8; PRD.md methodology revision item 5)."""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
from sqlalchemy import inspect as sa_inspect

import datagen.load_to_postgres as loader_module

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_no_ground_truth_column_anywhere_in_application_schema(db_engine):
    inspector = sa_inspect(db_engine)
    for table_name in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns(table_name)}
        assert "ground_truth_scenario" not in columns, f"{table_name} leaks ground_truth_scenario"
        assert "ground_truth_failure_mode" not in columns, f"{table_name} leaks ground_truth_failure_mode"


def test_no_ground_truth_source_value_possible_in_failure_labels():
    from backend.app.models.enums import FailureLabelSource

    assert "ground_truth" not in [m.value for m in FailureLabelSource]


def test_loader_source_never_references_the_validation_directory():
    """Structural check: none of the loader's actual code (function bodies,
    not the module's explanatory docstring) reads validation_ground_truth
    .parquet or generation_manifest.json, so leakage can't happen even if
    someone edits it carelessly without re-reading this test."""
    functions_to_check = [
        loader_module._rows_from_parquet,
        loader_module.truncate_all,
        loader_module.load_dataset,
        loader_module.main,
    ]
    for fn in functions_to_check:
        source = inspect.getsource(fn)
        assert "validation_ground_truth" not in source, f"{fn.__name__} references validation_ground_truth"
        assert "generation_manifest" not in source, f"{fn.__name__} references generation_manifest"


def test_validation_artifact_exists_and_is_separate_from_application_dir(dev_data_dir):
    validation_path = dev_data_dir / "dev" / "validation_ground_truth.parquet"
    manifest_path = dev_data_dir / "dev" / "generation_manifest.json"
    application_dir = dev_data_dir / "dev" / "application"

    assert validation_path.exists()
    assert manifest_path.exists()
    assert validation_path.parent != application_dir
    assert not (application_dir / "validation_ground_truth.parquet").exists()


def test_validation_artifact_has_expected_columns_and_planted_scenarios(dev_data_dir):
    df = pd.read_parquet(dev_data_dir / "dev" / "validation_ground_truth.parquet")
    assert set(df.columns) == {"session_id", "ground_truth_scenario", "ground_truth_failure_mode"}

    expected_scenarios = {
        "baseline",
        "exploratory_uplift",
        "overclarify_v2",
        "android_latency",
        "monitor_constraint_regression_v2",
        "tool_selection_v2_improved",
    }
    assert set(df.ground_truth_scenario.unique()) == expected_scenarios
    # every planted scenario actually fired at least once in the dev dataset
    for scenario in expected_scenarios - {"baseline"}:
        assert (df.ground_truth_scenario == scenario).sum() > 0, f"{scenario} never fired"


def test_application_sessions_row_count_matches_validation_row_count(dev_data_dir):
    app_sessions = pd.read_parquet(dev_data_dir / "dev" / "application" / "sessions.parquet")
    gt = pd.read_parquet(dev_data_dir / "dev" / "validation_ground_truth.parquet")
    assert len(app_sessions) == len(gt)
    assert set(app_sessions.session_id) == set(gt.session_id)
