"""Stage 4 task 3: metrics loadable from a simple JSON config file, not
just hand-written Python dataclass literals. Exercises
backend.core.config.load_metric_config directly against small synthetic
config files (not the real support domain's metrics.json, so this suite
does not depend on that file's contents) and separately proves the real
support domain config parses to the expected shape."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.analytics.experiment_results import analyze_metric
from backend.core.config import load_metric_config


@pytest.fixture
def tmp_config(tmp_path) -> Path:
    config = {
        "metrics": [
            {
                "name": "widget_rate",
                "label": "Widget Rate",
                "type": "rate",
                "direction": "higher_is_better",
                "semantic_class": "outcome",
                "inference_unit": "user",
                "value_column": "widgeted",
                "eligibility": None,
            },
            {
                "name": "latency_seconds",
                "label": "Latency",
                "type": "continuous",
                "direction": "lower_is_better",
                "semantic_class": "post_treatment_mechanism",
                "inference_unit": "user",
                "value_column": "latency",
                "eligibility": {"kind": "not_null", "column": "latency"},
            },
            {
                "name": "click_rate_of_shown",
                "label": "Click Rate",
                "type": "rate",
                "direction": "higher_is_better",
                "semantic_class": "outcome",
                "inference_unit": "user",
                "value_column": "clicked",
                "eligibility": {"kind": "equals", "column": "shown", "value": 1},
            },
            {
                "name": "big_order_rate",
                "label": "Big Order Rate",
                "type": "rate",
                "direction": "higher_is_better",
                "semantic_class": "outcome",
                "inference_unit": "user",
                "value_column": "big_order",
                "eligibility": {"kind": "gte", "column": "order_count", "value": 3},
            },
            {
                "name": "region",
                "label": "Region",
                "type": "ratio",
                "direction": "higher_is_better",
                "semantic_class": "pre_treatment",
                "inference_unit": "n/a (dimension, not a metric)",
                "is_inferential": False,
                "cluster_stat_shape": None,
                "value_column": None,
            },
        ]
    }
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_load_metric_config_produces_metric_definitions_with_stage4_fields(tmp_config):
    definitions, _ = load_metric_config(tmp_config)
    by_name = {m.name: m for m in definitions}

    assert by_name["widget_rate"].label == "Widget Rate"
    assert by_name["widget_rate"].metric_type == "rate"
    assert by_name["widget_rate"].direction == "higher_is_better"
    assert by_name["widget_rate"].is_rate_metric is True

    assert by_name["latency_seconds"].direction == "lower_is_better"
    assert by_name["latency_seconds"].is_rate_metric is False

    assert by_name["region"].semantic_class == "pre_treatment"
    assert by_name["region"].is_inferential is False


def test_load_metric_config_pure_dimension_entries_are_not_in_value_columns(tmp_config):
    _, value_columns = load_metric_config(tmp_config)
    assert "region" not in value_columns
    assert set(value_columns) == {"widget_rate", "latency_seconds", "click_rate_of_shown", "big_order_rate"}
    assert value_columns["widget_rate"] == ("widgeted", None)


def test_load_metric_config_not_null_eligibility_matches_hand_written_equivalent(tmp_config):
    _, value_columns = load_metric_config(tmp_config)
    _, eligibility_fn = value_columns["latency_seconds"]
    df = pd.DataFrame({"latency": [1.0, None, 3.0]})
    pd.testing.assert_series_equal(eligibility_fn(df), df["latency"].notna(), check_names=False)


def test_load_metric_config_equals_eligibility_matches_hand_written_equivalent(tmp_config):
    _, value_columns = load_metric_config(tmp_config)
    _, eligibility_fn = value_columns["click_rate_of_shown"]
    df = pd.DataFrame({"shown": [1, 0, 1]})
    pd.testing.assert_series_equal(eligibility_fn(df), df["shown"] == 1, check_names=False)


def test_load_metric_config_gte_eligibility_matches_hand_written_equivalent(tmp_config):
    _, value_columns = load_metric_config(tmp_config)
    _, eligibility_fn = value_columns["big_order_rate"]
    df = pd.DataFrame({"order_count": [1, 3, 5]})
    pd.testing.assert_series_equal(eligibility_fn(df), df["order_count"] >= 3, check_names=False)


def test_load_metric_config_rejects_unknown_eligibility_kind(tmp_path):
    config = {
        "metrics": [
            {"name": "x", "value_column": "x_col", "eligibility": {"kind": "regex_match", "column": "x_col"}}
        ]
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError):
        load_metric_config(path)


def test_config_loaded_metric_works_through_analyze_metric_unchanged(tmp_config):
    """The config-loaded shape (MetricDefinition + value_columns dict) must
    be usable by the same analyze_metric() every hand-written domain uses —
    no special-casing for config-loaded metrics."""
    definitions, value_columns = load_metric_config(tmp_config)
    metric = next(m for m in definitions if m.name == "widget_rate")
    df = pd.DataFrame(
        {
            "agent_version": ["v1"] * 12 + ["v2"] * 12,
            "user_id": [f"u{i}" for i in range(24)],
            "widgeted": [1] * 6 + [0] * 6 + [1] * 9 + [0] * 3,
        }
    )
    result = analyze_metric(df, metric, metric_value_columns=value_columns)
    assert result.n_users_v1 == 12
    assert result.n_users_v2 == 12
    assert result.session_value_v1 == pytest.approx(0.5)
    assert result.session_value_v2 == pytest.approx(0.75)


def test_real_support_domain_metrics_config_loads_and_matches_the_adapter():
    """Regression: the actual backend/domains/support/metrics.json this
    project ships parses into exactly what SupportAdapter exposes."""
    from backend.domains.support.metrics import SUPPORT_METRIC_REGISTRY, SUPPORT_METRIC_VALUE_COLUMNS

    names = {m.name for m in SUPPORT_METRIC_REGISTRY}
    assert names == {"resolution_rate", "escalation_rate", "csat_score", "handle_time_seconds", "ticket_category"}
    assert set(SUPPORT_METRIC_VALUE_COLUMNS) == {"resolution_rate", "escalation_rate", "csat_score", "handle_time_seconds"}

    resolution = next(m for m in SUPPORT_METRIC_REGISTRY if m.name == "resolution_rate")
    assert resolution.label == "Resolution Rate"
    assert resolution.direction == "higher_is_better"

    ticket_category = next(m for m in SUPPORT_METRIC_REGISTRY if m.name == "ticket_category")
    assert ticket_category.semantic_class == "pre_treatment"
