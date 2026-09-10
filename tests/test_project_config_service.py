"""Stage 12 task 5: config validation logic — pure, no database (a
project's own get/upsert round-trip is covered at the API level in
tests/test_project_config_api.py, where real ingested context and a
real adapter are naturally available)."""

from __future__ import annotations

from backend.project_config.service import VALID_EVENT_TYPES, validate_project_config


def _validate(**overrides):
    defaults = dict(
        primary_metric=None, metrics_json=None, guardrails_json=None, segment_dimensions_json=None,
        economics_json=None, enabled_notification_rules=None, effective_metric_names=set(), known_context_keys=set(),
    )
    defaults.update(overrides)
    return validate_project_config(**defaults)


def test_empty_config_is_valid():
    assert _validate() == []


def test_valid_metrics_config_produces_no_issues():
    metrics = {"metrics": [{"name": "resolution_rate", "value_column": "resolved"}]}
    assert _validate(metrics_json=metrics) == []


def test_malformed_metrics_config_is_reported():
    issues = _validate(metrics_json={"not_metrics_key": []})
    assert len(issues) == 1
    assert issues[0].field == "metrics"


def test_guardrail_referencing_unknown_metric_is_reported():
    guardrails = {"guardrails": [{"name": "g1", "metric": "not_a_real_metric", "column": "x", "aggregation": "cluster_mean", "threshold": 0.1}]}
    issues = _validate(guardrails_json=guardrails, effective_metric_names={"resolution_rate"})
    assert len(issues) == 1
    assert issues[0].field == "guardrails"
    assert "not_a_real_metric" in issues[0].message


def test_guardrail_referencing_known_metric_is_valid():
    guardrails = {"guardrails": [{"name": "g1", "metric": "resolution_rate", "column": "resolved", "aggregation": "cluster_mean", "threshold": 0.1}]}
    assert _validate(guardrails_json=guardrails, effective_metric_names={"resolution_rate"}) == []


def test_malformed_guardrails_config_is_reported():
    issues = _validate(guardrails_json={"guardrails": [{"name": "g1"}]})  # missing required "column"/"aggregation"/"threshold"
    assert len(issues) == 1
    assert issues[0].field == "guardrails"


def test_segment_dimension_not_in_known_context_keys_is_reported():
    issues = _validate(segment_dimensions_json={"ticket_category": ["billing"]}, known_context_keys={"other_key"})
    assert len(issues) == 1
    assert issues[0].field == "segment_dimensions"


def test_segment_dimension_in_known_context_keys_is_valid():
    assert _validate(segment_dimensions_json={"ticket_category": ["billing"]}, known_context_keys={"ticket_category"}) == []


def test_segment_dimension_check_skipped_when_no_data_ingested_yet():
    # known_context_keys empty (no sessions at all) -> can't check yet,
    # never a hard error before a project's first ingest.
    assert _validate(segment_dimensions_json={"ticket_category": ["billing"]}, known_context_keys=set()) == []


def test_primary_metric_not_in_effective_metrics_is_reported():
    issues = _validate(primary_metric="not_a_real_metric", effective_metric_names={"resolution_rate"})
    assert len(issues) == 1
    assert issues[0].field == "primary_metric"


def test_primary_metric_in_effective_metrics_is_valid():
    assert _validate(primary_metric="resolution_rate", effective_metric_names={"resolution_rate"}) == []


def test_economics_missing_success_column_is_reported():
    issues = _validate(economics_json={"cost_column": "cost_usd"})
    assert len(issues) == 1
    assert issues[0].field == "economics"


def test_economics_with_success_column_is_valid():
    assert _validate(economics_json={"success_column": "resolved"}) == []


def test_unknown_notification_event_type_is_reported():
    issues = _validate(enabled_notification_rules=["ROLLBACK", "NOT_A_REAL_EVENT"])
    assert len(issues) == 1
    assert issues[0].field == "enabled_notification_rules"


def test_all_valid_event_types_pass():
    assert _validate(enabled_notification_rules=sorted(VALID_EVENT_TYPES)) == []


def test_multiple_issues_are_all_reported_together():
    issues = _validate(
        primary_metric="unknown_metric",
        guardrails_json={"guardrails": [{"name": "g1", "metric": "unknown_metric", "column": "x", "aggregation": "cluster_mean", "threshold": 0.1}]},
        economics_json={},
        effective_metric_names={"resolution_rate"},
    )
    fields = {i.field for i in issues}
    assert fields == {"primary_metric", "guardrails", "economics"}
