"""Stage 11 tasks 1-2/9: monitoring job execution at the service layer —
scheduled execution (list_due_configs/run_due_jobs-equivalent), duplicate
-run prevention via the Postgres advisory lock, failed-job persistence,
and tenant isolation. Calls backend.monitoring.service directly (not
through the API) so these are fast, deterministic tests that never wait
on a real background thread's poll interval."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from backend.app.db import get_database_url
from backend.monitoring.service import (
    _lock_key,
    create_monitoring_config,
    get_latest_monitoring_run,
    list_due_configs,
    list_monitoring_runs,
    run_monitoring_job,
)
from tests._connector_test_helpers import new_support_project


def _ingest_release_fixture(api_client, project_id: str, tag: str) -> str:
    """A large, deterministic v1-vs-v2 support fixture (same ratios as
    tests/test_alerts_integration.py's own) so evaluate_and_persist_release
    reliably reaches ROLLBACK -- exercised here purely to prove the
    monitoring job runs the SAME release logic, not to test the verdict
    itself again."""

    def session(sid: str, version: str, outcome: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"mon-exp-{tag}", "agent_version": version, "external_user_id": f"user-{sid}",
            "started_at": "2026-09-01T00:00:00", "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
        }

    sessions = [session(f"mon-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 9 else "escalated") for i in range(40)]
    sessions += [session(f"mon-{tag}-v2-{i}", "v2", "resolved" if i % 10 < 6 else "escalated") for i in range(40)]
    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"mon-exp-{tag}", "name": f"Monitoring Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    return next(e["experiment_id"] for e in experiments if e["name"] == f"Monitoring Test {tag}")


def _adapter_factory(engine):
    from backend.domains.support.adapter import SupportAdapter

    def factory(domain: str, project_id: str | None):
        return SupportAdapter(engine, project_id=project_id)

    return factory


def test_scheduled_monitoring_execution_runs_and_persists_evaluation(api_client, support_project_id):
    tag = f"sched-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_release_fixture(api_client, support_project_id, tag)
    engine = create_engine(get_database_url())

    config = create_monitoring_config(engine, support_project_id, "support", exp_id, "resolution_rate", cadence_seconds=1)
    assert list_due_configs(engine).__len__() >= 1  # a brand-new config with no prior run is always due

    outcome = run_monitoring_job(engine, config, _adapter_factory(engine))
    assert outcome.status == "succeeded"
    assert outcome.release_evaluation_id is not None

    runs = list_monitoring_runs(engine, support_project_id, config.config_id)
    assert len(runs) == 1
    assert runs[0].status == "succeeded"
    assert runs[0].completed_at is not None


def test_failed_job_is_persisted_with_a_reason(api_client, support_project_id):
    tag = f"fail-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_release_fixture(api_client, support_project_id, tag)
    engine = create_engine(get_database_url())
    # evaluate_and_persist_release (unlike the API layer's own
    # _validate_primary_metric) does no upfront metric-name validation --
    # get_metric() raises deep inside run_investigation, a real failure
    # the job must record as status="failed" with a reason, never silently
    # swallow it or leave "running" forever.
    config = create_monitoring_config(engine, support_project_id, "support", exp_id, "not_a_real_metric", cadence_seconds=60)

    outcome = run_monitoring_job(engine, config, _adapter_factory(engine))
    assert outcome.status == "failed"
    assert outcome.failure_reason
    assert outcome.release_evaluation_id is None

    latest = get_latest_monitoring_run(engine, support_project_id, config.config_id)
    assert latest.status == "failed"
    assert latest.failure_reason == outcome.failure_reason


def test_duplicate_concurrent_run_is_prevented_and_recorded(api_client, support_project_id):
    tag = f"lock-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_release_fixture(api_client, support_project_id, tag)
    engine = create_engine(get_database_url())
    config = create_monitoring_config(engine, support_project_id, "support", exp_id, "not_a_real_metric", cadence_seconds=60)

    key = _lock_key(config.project_id, config.experiment_id)
    holder = engine.connect()
    try:
        acquired = holder.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
        assert acquired is True  # simulates another in-flight run already holding the lock

        outcome = run_monitoring_job(engine, config, _adapter_factory(engine))
        assert outcome.status == "skipped_duplicate"
        assert "already in progress" in outcome.failure_reason
        assert outcome.release_evaluation_id is None
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
        holder.close()

    # Lock released -- a second attempt now proceeds normally (still fails,
    # since the experiment doesn't exist, but NOT as a duplicate skip).
    second = run_monitoring_job(engine, config, _adapter_factory(engine))
    assert second.status == "failed"


def test_monitoring_runs_are_project_scoped(test_identity, support_project_id):
    engine = create_engine(get_database_url())
    other_project_id = new_support_project(test_identity, "Monitoring Isolation Project")
    experiment_id = f"isoexp-{uuid.uuid4().hex[:8]}"

    config_a = create_monitoring_config(engine, support_project_id, "support", experiment_id, "resolution_rate", cadence_seconds=60)
    config_b = create_monitoring_config(engine, other_project_id, "support", experiment_id, "resolution_rate", cadence_seconds=60)

    run_monitoring_job(engine, config_a, _adapter_factory(engine))
    run_monitoring_job(engine, config_b, _adapter_factory(engine))

    runs_a = list_monitoring_runs(engine, support_project_id, config_a.config_id)
    runs_b = list_monitoring_runs(engine, other_project_id, config_b.config_id)
    assert len(runs_a) == 1
    assert len(runs_b) == 1
    assert runs_a[0].run_id != runs_b[0].run_id

    # Project A can never see project B's run history under its own config id.
    assert list_monitoring_runs(engine, support_project_id, config_b.config_id) == []
