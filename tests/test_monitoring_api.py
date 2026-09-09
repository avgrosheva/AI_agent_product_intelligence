"""Stage 11 tasks 1-2/7/9: the monitoring configuration/run-history API,
end to end through the real routes — creating a config, triggering an
on-demand run (dispatched via FastAPI BackgroundTasks, so the request
itself never blocks on the Investigation engine — Starlette's TestClient
runs a response's background tasks synchronously before returning,
verified separately, so the triggered run has already finished by the
time the test's own `.post()` call returns), run history, latest status,
and tenant isolation of monitoring resources themselves."""

from __future__ import annotations

import uuid

from tests._connector_test_helpers import new_support_project


def _ingest_release_fixture(api_client, project_id: str, tag: str) -> str:
    def session(sid: str, version: str, outcome: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"monapi-exp-{tag}", "agent_version": version, "external_user_id": f"user-{sid}",
            "started_at": "2026-09-01T00:00:00", "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
        }

    sessions = [session(f"monapi-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 9 else "escalated") for i in range(40)]
    sessions += [session(f"monapi-{tag}-v2-{i}", "v2", "resolved" if i % 10 < 6 else "escalated") for i in range(40)]
    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"monapi-exp-{tag}", "name": f"Monitoring API Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    return next(e["experiment_id"] for e in experiments if e["name"] == f"Monitoring API Test {tag}")


def test_create_and_list_monitoring_config(api_client, support_project_id):
    tag = f"cfg-{uuid.uuid4().hex[:8]}"
    body = {"domain": "support", "experiment_id": f"exp-{tag}", "primary_metric": "resolution_rate", "cadence_seconds": 3600, "window_hours": 24}
    resp = api_client.post(f"/api/v1/monitoring/configs?project_id={support_project_id}", json=body)
    assert resp.status_code == 201
    created = resp.json()
    assert created["cadence_seconds"] == 3600
    assert created["window_hours"] == 24
    assert created["enabled"] is True

    listing = api_client.get(f"/api/v1/monitoring/configs?project_id={support_project_id}&domain=support")
    assert listing.status_code == 200
    assert any(c["config_id"] == created["config_id"] for c in listing.json()["configs"])


def test_run_now_executes_in_background_and_is_visible_in_history(api_client, support_project_id):
    tag = f"runnow-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_release_fixture(api_client, support_project_id, tag)
    config_resp = api_client.post(
        f"/api/v1/monitoring/configs?project_id={support_project_id}",
        json={"domain": "support", "experiment_id": exp_id, "primary_metric": "resolution_rate", "cadence_seconds": 3600},
    )
    config_id = config_resp.json()["config_id"]

    trigger = api_client.post(f"/api/v1/monitoring/configs/{config_id}/run-now?project_id={support_project_id}&domain=support")
    assert trigger.status_code == 202
    assert trigger.json()["config_id"] == config_id

    latest = api_client.get(f"/api/v1/monitoring/configs/{config_id}/latest?project_id={support_project_id}&domain=support")
    assert latest.status_code == 200
    latest_body = latest.json()
    assert latest_body["status"] == "succeeded"
    assert latest_body["release_evaluation_id"] is not None

    history = api_client.get(f"/api/v1/monitoring/configs/{config_id}/runs?project_id={support_project_id}&domain=support")
    assert history.status_code == 200
    assert len(history.json()["runs"]) == 1


def test_latest_status_404s_before_any_run(api_client, support_project_id):
    resp = api_client.post(
        f"/api/v1/monitoring/configs?project_id={support_project_id}",
        json={"domain": "support", "experiment_id": f"never-run-{uuid.uuid4().hex[:8]}", "primary_metric": "resolution_rate", "cadence_seconds": 3600},
    )
    config_id = resp.json()["config_id"]
    latest = api_client.get(f"/api/v1/monitoring/configs/{config_id}/latest?project_id={support_project_id}&domain=support")
    assert latest.status_code == 404


def test_monitoring_configs_are_project_scoped(api_client, support_project_id, test_identity):
    other_project_id = new_support_project(test_identity, "Monitoring API Isolation Project")
    resp = api_client.post(
        f"/api/v1/monitoring/configs?project_id={support_project_id}",
        json={"domain": "support", "experiment_id": f"scoped-{uuid.uuid4().hex[:8]}", "primary_metric": "resolution_rate", "cadence_seconds": 3600},
    )
    config_id = resp.json()["config_id"]

    # Another project belonging to the SAME caller cannot read a config
    # that belongs to a different project.
    cross = api_client.get(f"/api/v1/monitoring/configs/{config_id}/latest?project_id={other_project_id}&domain=support")
    assert cross.status_code == 404

    listing_other = api_client.get(f"/api/v1/monitoring/configs?project_id={other_project_id}&domain=support")
    assert all(c["config_id"] != config_id for c in listing_other.json()["configs"])
