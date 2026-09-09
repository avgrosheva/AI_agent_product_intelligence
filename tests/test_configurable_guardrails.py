"""Stage 4 task 4: guardrails loadable from a simple JSON config file
(metric, threshold, direction, severity, enabled/disabled), evaluated by
the same generic evaluate_guardrails() every hand-written domain uses."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from backend.core.config import load_guardrail_config
from backend.core.guardrails import GuardrailDefinition, evaluate_guardrails


@pytest.fixture
def tmp_config(tmp_path):
    config = {
        "guardrails": [
            {
                "name": "latency_ratio",
                "metric": "p95_latency_ms",
                "column": "latency_ms",
                "aggregation": "p95_raw",
                "kind": "ratio",
                "direction": "increase_is_bad",
                "threshold": 1.15,
                "severity": "blocking",
                "enabled": True,
            },
            {
                "name": "satisfaction_floor",
                "metric": "satisfaction_score",
                "column": "satisfaction",
                "aggregation": "cluster_mean",
                "kind": "absolute",
                "direction": "decrease_is_bad",
                "threshold": 0.1,
                "severity": "warning",
                "enabled": True,
            },
            {
                "name": "disabled_guardrail",
                "metric": "unused_metric",
                "column": "unused_column",
                "aggregation": "cluster_mean",
                "kind": "ratio",
                "direction": "increase_is_bad",
                "threshold": 1.0,
                "enabled": False,
            },
        ]
    }
    path = tmp_path / "guardrails.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_load_guardrail_config_produces_definitions_with_stage4_fields(tmp_config):
    definitions = load_guardrail_config(tmp_config)
    by_name = {g.name: g for g in definitions}

    latency = by_name["latency_ratio"]
    assert latency.metric == "p95_latency_ms"
    assert latency.kind == "ratio"
    assert latency.direction == "increase_is_bad"
    assert latency.severity == "blocking"
    assert latency.enabled is True

    satisfaction = by_name["satisfaction_floor"]
    assert satisfaction.severity == "warning"
    assert satisfaction.direction == "decrease_is_bad"

    assert by_name["disabled_guardrail"].enabled is False


def test_evaluate_guardrails_skips_disabled_definitions(tmp_config):
    definitions = load_guardrail_config(tmp_config)
    df = pd.DataFrame(
        {
            "agent_version": ["v1"] * 10 + ["v2"] * 10,
            "user_id": [f"u{i}" for i in range(20)],
            "latency_ms": [100.0] * 10 + [100.0] * 10,
            "satisfaction": [4.0] * 10 + [4.0] * 10,
            "unused_column": [1.0] * 20,
        }
    )
    report = evaluate_guardrails(df, definitions)
    names = {c.name for c in report.checks}
    assert names == {"latency_ratio", "satisfaction_floor"}
    assert "disabled_guardrail" not in names


def test_decrease_is_bad_direction_flags_a_drop_below_threshold():
    definitions = [
        GuardrailDefinition(
            name="satisfaction_floor", column="satisfaction", aggregation="cluster_mean",
            kind="absolute", direction="decrease_is_bad", threshold=0.1,
        )
    ]
    df = pd.DataFrame({
        "agent_version": ["v1"] * 10 + ["v2"] * 10,
        "user_id": [f"u{i}" for i in range(20)],
        "satisfaction": [4.0] * 10 + [3.5] * 10,
    })
    report = evaluate_guardrails(df, definitions)
    assert report.checks[0].breached is True

    df_ok = pd.DataFrame({
        "agent_version": ["v1"] * 10 + ["v2"] * 10,
        "user_id": [f"u{i}" for i in range(20)],
        "satisfaction": [4.0] * 10 + [3.95] * 10,
    })
    report_ok = evaluate_guardrails(df_ok, definitions)
    assert report_ok.checks[0].breached is False


def test_warning_severity_breach_is_reported_but_never_blocking():
    definitions = [
        GuardrailDefinition(
            name="warn_only", column="x", aggregation="cluster_mean",
            kind="absolute", direction="increase_is_bad", threshold=0.0, severity="warning",
        )
    ]
    df = pd.DataFrame({
        "agent_version": ["v1"] * 10 + ["v2"] * 10,
        "user_id": [f"u{i}" for i in range(20)],
        "x": [0.0] * 10 + [1.0] * 10,
    })
    report = evaluate_guardrails(df, definitions)
    assert report.checks[0].breached is True
    assert report.any_breach is False  # not "blocking" severity
    assert report.any_warning_breach is True


def test_real_support_domain_guardrails_config_loads_and_matches_the_adapter():
    """Regression: the actual backend/domains/support/guardrails.json this
    project ships parses into exactly what SupportAdapter exposes."""
    from backend.domains.support.guardrails import SUPPORT_GUARDRAILS

    assert len(SUPPORT_GUARDRAILS) == 1
    g = SUPPORT_GUARDRAILS[0]
    assert g.name == "escalation_rate_guardrail"
    assert g.metric == "escalation_rate"
    assert g.kind == "absolute"
    assert g.direction == "increase_is_bad"
    assert g.threshold == 0.05
    assert g.enabled is True
