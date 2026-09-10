"""Stage 11 tasks 5-6: data-quality thresholds and the connector_runs log
they read. Uses real ingested sessions/metrics (via the generic ingestion
API, a throwaway support project per test) rather than mocking the
computation, so the thresholds are proven against real stored rows."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from backend.app.db import get_database_url
from backend.quality.service import compute_data_quality_report, record_connector_run
from tests._connector_test_helpers import new_support_project


def _payload(tag: str, sessions: list[dict]) -> dict:
    return {
        "domain": "support",
        "experiments": [{"external_experiment_id": f"quality-exp-{tag}", "name": f"Quality Test {tag}", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": sessions,
    }


def _session(sid: str, version: str, outcome_label: str | None, with_metric: bool, tag: str) -> dict:
    return {
        "external_session_id": sid,
        "external_experiment_id": f"quality-exp-{tag}",
        "agent_version": version,
        "started_at": "2026-09-01T00:00:00",
        "outcome": {"label": outcome_label or "resolved", "metrics": []},
        "metrics": [{"name": "handle_time_seconds", "value": 100.0}] if with_metric else [],
    }


def test_no_ingested_data_is_healthy_not_applicable(api_client, test_identity):
    engine = create_engine(get_database_url())
    project_id = new_support_project(test_identity, "Quality Empty Project")
    report = compute_data_quality_report(engine, project_id, "support")
    assert report.status == "healthy"
    assert report.checks[0].status == "not_applicable"


def test_fully_healthy_balanced_dataset(api_client, test_identity):
    tag = f"healthy-{uuid.uuid4().hex[:8]}"
    project_id = new_support_project(test_identity, "Quality Healthy Project")
    sessions = [_session(f"{tag}-v1-{i}", "v1", "resolved", True, tag) for i in range(10)] + [_session(f"{tag}-v2-{i}", "v2", "resolved", True, tag) for i in range(10)]
    resp = api_client.post("/api/v1/ingest/sessions", json=_payload(tag, sessions), params={"project_id": project_id})
    assert resp.status_code == 201

    engine = create_engine(get_database_url())
    report = compute_data_quality_report(engine, project_id, "support")
    assert report.status == "healthy"
    by_name = {c.name: c for c in report.checks}
    assert by_name["missing_outcome_rate"].value == 0.0
    assert by_name["missing_metric_coverage_rate"].value == 0.0
    assert by_name["sessions_without_version_rate"].value == 0.0
    assert by_name["experiment_arm_balance_ratio"].value == 1.0


def test_missing_metric_coverage_triggers_critical(api_client, test_identity):
    tag = f"nometrics-{uuid.uuid4().hex[:8]}"
    project_id = new_support_project(test_identity, "Quality No-Metrics Project")
    sessions = [_session(f"{tag}-v1-{i}", "v1", "resolved", False, tag) for i in range(10)] + [_session(f"{tag}-v2-{i}", "v2", "resolved", False, tag) for i in range(10)]
    resp = api_client.post("/api/v1/ingest/sessions", json=_payload(tag, sessions), params={"project_id": project_id})
    assert resp.status_code == 201

    engine = create_engine(get_database_url())
    report = compute_data_quality_report(engine, project_id, "support")
    by_name = {c.name: c for c in report.checks}
    assert by_name["missing_metric_coverage_rate"].value == 1.0
    assert by_name["missing_metric_coverage_rate"].status == "critical"
    assert report.status == "critical"


def test_arm_imbalance_and_missing_arm(api_client, test_identity):
    tag = f"imbalance-{uuid.uuid4().hex[:8]}"
    project_id = new_support_project(test_identity, "Quality Imbalance Project")
    # 10 sessions in v1 only -- no v2 arm at all.
    sessions = [_session(f"{tag}-v1-{i}", "v1", "resolved", True, tag) for i in range(10)]
    resp = api_client.post("/api/v1/ingest/sessions", json=_payload(tag, sessions), params={"project_id": project_id})
    assert resp.status_code == 201

    engine = create_engine(get_database_url())
    report = compute_data_quality_report(engine, project_id, "support")
    by_name = {c.name: c for c in report.checks}
    assert by_name["experiment_arm_balance_ratio"].status == "critical"
    assert report.status == "critical"


def test_connector_import_failures_recorded_and_flagged(api_client, test_identity):
    project_id = new_support_project(test_identity, "Quality Connector Failure Project")
    # This project has no ingested_sessions at all, so the report would
    # normally short-circuit "healthy/not_applicable" -- ingest one
    # trivial session so the rest of the checks actually run and the
    # connector-failure signal can be observed independent of that.
    tag = f"connfail-{uuid.uuid4().hex[:8]}"
    sessions = [_session(f"{tag}-v1-0", "v1", "resolved", True, tag), _session(f"{tag}-v2-0", "v2", "resolved", True, tag)]
    api_client.post("/api/v1/ingest/sessions", json=_payload(tag, sessions), params={"project_id": project_id})

    engine = create_engine(get_database_url())
    record_connector_run(engine, project_id, "support", "langfuse", succeeded=False, failure_reason="simulated outage")
    record_connector_run(engine, project_id, "support", "langfuse", succeeded=False, failure_reason="simulated outage")
    record_connector_run(engine, project_id, "support", "langfuse", succeeded=False, failure_reason="simulated outage")

    report = compute_data_quality_report(engine, project_id, "support")
    by_name = {c.name: c for c in report.checks}
    assert by_name["connector_import_failure_count"].value == 3.0
    assert by_name["connector_import_failure_count"].status == "critical"
    assert report.status == "critical"


def test_business_enrichment_unmatched_and_duplicate_rates_come_from_most_recent_run(api_client, test_identity):
    project_id = new_support_project(test_identity, "Quality Business Enrichment Project")
    tag = f"biz-{uuid.uuid4().hex[:8]}"
    sessions = [_session(f"{tag}-v1-0", "v1", "resolved", True, tag), _session(f"{tag}-v2-0", "v2", "resolved", True, tag)]
    api_client.post("/api/v1/ingest/sessions", json=_payload(tag, sessions), params={"project_id": project_id})

    engine = create_engine(get_database_url())
    record_connector_run(engine, project_id, "support", "postgres_business", succeeded=True, rows_fetched=100, matched_rows=50, unmatched_rows=50, validation_error_count=0)

    report = compute_data_quality_report(engine, project_id, "support")
    by_name = {c.name: c for c in report.checks}
    assert by_name["unmatched_business_data_rate"].value == 0.5
    assert by_name["unmatched_business_data_rate"].status == "critical"


def test_ingestion_freshness_reflects_most_recent_created_at(api_client, test_identity):
    project_id = new_support_project(test_identity, "Quality Freshness Project")
    tag = f"fresh-{uuid.uuid4().hex[:8]}"
    sessions = [_session(f"{tag}-v1-0", "v1", "resolved", True, tag), _session(f"{tag}-v2-0", "v2", "resolved", True, tag)]
    resp = api_client.post("/api/v1/ingest/sessions", json=_payload(tag, sessions), params={"project_id": project_id})
    assert resp.status_code == 201

    engine = create_engine(get_database_url())
    report = compute_data_quality_report(engine, project_id, "support")
    by_name = {c.name: c for c in report.checks}
    assert by_name["ingestion_freshness_hours"].value is not None
    assert by_name["ingestion_freshness_hours"].value < 1.0  # ingested moments ago
    assert by_name["ingestion_freshness_hours"].status == "healthy"


def test_data_quality_report_is_project_scoped(api_client, test_identity):
    """Stage 11 task 8/9: tenant isolation for the data-quality report --
    one project's bad data quality must never leak into another's report."""
    tag = f"isoquality-{uuid.uuid4().hex[:8]}"
    healthy_project = new_support_project(test_identity, "Quality Isolation Healthy")
    critical_project = new_support_project(test_identity, "Quality Isolation Critical")

    healthy_sessions = [_session(f"{tag}-h-v1-{i}", "v1", "resolved", True, f"{tag}-h") for i in range(5)] + [
        _session(f"{tag}-h-v2-{i}", "v2", "resolved", True, f"{tag}-h") for i in range(5)
    ]
    api_client.post("/api/v1/ingest/sessions", json=_payload(f"{tag}-h", healthy_sessions), params={"project_id": healthy_project})

    critical_sessions = [_session(f"{tag}-c-v1-{i}", "v1", "resolved", False, f"{tag}-c") for i in range(5)] + [
        _session(f"{tag}-c-v2-{i}", "v2", "resolved", False, f"{tag}-c") for i in range(5)
    ]
    api_client.post("/api/v1/ingest/sessions", json=_payload(f"{tag}-c", critical_sessions), params={"project_id": critical_project})

    engine = create_engine(get_database_url())
    assert compute_data_quality_report(engine, healthy_project, "support").status == "healthy"
    assert compute_data_quality_report(engine, critical_project, "support").status == "critical"


def _session_at(sid: str, version: str, with_metric: bool, tag: str, started_at: str) -> dict:
    return {
        "external_session_id": sid, "external_experiment_id": f"quality-exp-{tag}", "agent_version": version,
        "started_at": started_at, "outcome": {"label": "resolved", "metrics": []},
        "metrics": [{"name": "handle_time_seconds", "value": 100.0}] if with_metric else [],
    }


def test_window_scopes_missing_metric_coverage_to_the_window(api_client, test_identity):
    """Stage 13 task 7: old sessions (outside the window) have full
    metric coverage; recent sessions (inside the window) have none. The
    global (unwindowed) report should be mostly healthy; the windowed
    report, seeing only the metric-less recent sessions, must be critical."""
    from backend.core.analysis_window import AnalysisWindow

    tag = f"windq-{uuid.uuid4().hex[:8]}"
    project_id = new_support_project(test_identity, "Quality Window Project")
    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=10)).replace(tzinfo=None).isoformat()
    recent_ts = (now - timedelta(hours=1)).replace(tzinfo=None).isoformat()

    sessions = [_session_at(f"{tag}-old-{i}", "v1" if i % 2 else "v2", True, tag, old_ts) for i in range(20)]
    sessions += [_session_at(f"{tag}-recent-{i}", "v1" if i % 2 else "v2", False, tag, recent_ts) for i in range(10)]
    resp = api_client.post("/api/v1/ingest/sessions", json=_payload(tag, sessions), params={"project_id": project_id})
    assert resp.status_code == 201

    engine = create_engine(get_database_url())
    global_report = compute_data_quality_report(engine, project_id, "support")
    windowed_report = compute_data_quality_report(engine, project_id, "support", window=AnalysisWindow(start=now - timedelta(hours=6), end=now))

    global_by_name = {c.name: c for c in global_report.checks}
    windowed_by_name = {c.name: c for c in windowed_report.checks}

    assert global_by_name["missing_metric_coverage_rate"].value == pytest.approx(10 / 30)  # 10 of 30 total
    assert windowed_by_name["missing_metric_coverage_rate"].value == 1.0  # all 10 windowed sessions lack metrics
    assert windowed_by_name["missing_metric_coverage_rate"].status == "critical"


def test_ingestion_freshness_and_connector_failures_stay_global_regardless_of_window(api_client, test_identity):
    """Stage 13 task 7: freshness and connector-health checks must never
    be hidden by a narrow window — a stale integration or a connector
    outage that happened outside the window is still real and must still
    show up."""
    from backend.core.analysis_window import AnalysisWindow

    tag = f"windfresh-{uuid.uuid4().hex[:8]}"
    project_id = new_support_project(test_identity, "Quality Window Freshness Project")
    now = datetime.now(timezone.utc)
    recent_ts = now.replace(tzinfo=None).isoformat()

    sessions = [_session_at(f"{tag}-{i}", "v1" if i % 2 else "v2", True, tag, recent_ts) for i in range(10)]
    api_client.post("/api/v1/ingest/sessions", json=_payload(tag, sessions), params={"project_id": project_id})

    engine = create_engine(get_database_url())
    record_connector_run(engine, project_id, "support", "langfuse", succeeded=False, failure_reason="simulated outage")
    record_connector_run(engine, project_id, "support", "langfuse", succeeded=False, failure_reason="simulated outage")
    record_connector_run(engine, project_id, "support", "langfuse", succeeded=False, failure_reason="simulated outage")

    # A window that excludes ALL of this project's sessions (a narrow
    # slice far in the past) -- freshness and connector failures must
    # still be reported, unaffected.
    narrow_past_window = AnalysisWindow(start=now - timedelta(days=100), end=now - timedelta(days=99))
    report = compute_data_quality_report(engine, project_id, "support", window=narrow_past_window)
    by_name = {c.name: c for c in report.checks}

    assert by_name["ingestion_freshness_hours"].status == "healthy"  # sessions were ingested moments ago, globally
    assert by_name["connector_import_failure_count"].value == 3.0
    assert by_name["connector_import_failure_count"].status == "critical"
    assert report.status == "critical"  # the connector failures alone make the overall status critical

    # The window-scoped checks correctly show "no sessions in this window".
    assert by_name["missing_metric_coverage_rate"].status == "not_applicable"
