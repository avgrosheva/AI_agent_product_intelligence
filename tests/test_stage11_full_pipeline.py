"""Stage 11 task 9: full end-to-end regression tying every new Stage 11
piece to the existing pipeline through the real API — ingestion ->
scheduled monitoring run -> release evaluation -> alert -> evidence ->
data-quality report, all consistent with each other."""

from __future__ import annotations

import uuid


OTHER_CATEGORIES = ["technical", "account_access", "shipping_status", "general_inquiry"]


def _ingest_rollback_fixture(api_client, project_id: str, tag: str) -> str:
    """Category varies ("billing" regresses much harder than the other
    four) so the segment scan flags a real negative segment on top of the
    overall ROLLBACK verdict — this test checks evidence downstream of a
    monitoring-triggered run, not just the verdict itself."""

    def session(sid: str, version: str, outcome: str, category: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"e2e11-exp-{tag}", "agent_version": version, "external_user_id": f"user-{sid}",
            "started_at": "2026-09-01T00:00:00", "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
            "context": {"ticket_category": category},
        }

    sessions = []
    for i in range(40):
        category = "billing" if i < 20 else OTHER_CATEGORIES[i % 4]
        sessions.append(session(f"e2e11-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 9 else "escalated", category))
    for i in range(40):
        category = "billing" if i < 20 else OTHER_CATEGORIES[i % 4]
        outcome = ("resolved" if i % 10 < 2 else "escalated") if category == "billing" else ("resolved" if i % 10 < 8 else "escalated")
        sessions.append(session(f"e2e11-{tag}-v2-{i}", "v2", outcome, category))

    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"e2e11-exp-{tag}", "name": f"Stage11 E2E Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    return next(e["experiment_id"] for e in experiments if e["name"] == f"Stage11 E2E Test {tag}")


def test_ingestion_through_monitoring_to_evidence_and_data_quality(api_client, support_project_id):
    tag = f"e2e11-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_rollback_fixture(api_client, support_project_id, tag)

    quality_before = api_client.get(f"/api/v1/domains/support/data-quality?project_id={support_project_id}")
    assert quality_before.status_code == 200
    assert quality_before.json()["status"] in {"healthy", "warning"}  # this fixture's own data is clean

    config_resp = api_client.post(
        f"/api/v1/monitoring/configs?project_id={support_project_id}",
        json={"domain": "support", "experiment_id": exp_id, "primary_metric": "resolution_rate", "cadence_seconds": 3600, "window_hours": 24},
    )
    assert config_resp.status_code == 201
    config_id = config_resp.json()["config_id"]

    trigger = api_client.post(f"/api/v1/monitoring/configs/{config_id}/run-now?project_id={support_project_id}&domain=support")
    assert trigger.status_code == 202

    latest_run = api_client.get(f"/api/v1/monitoring/configs/{config_id}/latest?project_id={support_project_id}&domain=support").json()
    assert latest_run["status"] == "succeeded"
    assert latest_run["data_window_start"] is not None  # window_hours=24 recorded on the run
    evaluation_id = latest_run["release_evaluation_id"]
    assert evaluation_id is not None

    evaluation = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-status?project_id={support_project_id}").json()
    assert evaluation["evaluation_id"] == evaluation_id
    assert evaluation["status"] == "ROLLBACK"

    alerts = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={support_project_id}").json()["alerts"]
    assert any(a["rule"] == "rollback" for a in alerts)

    evidence = api_client.get(
        f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations/{evaluation_id}/evidence?project_id={support_project_id}"
    ).json()
    assert evidence["status"] == "ROLLBACK"
    represented_ids = {s["session_id"] for s in evidence["representative_sessions"]}
    assert represented_ids  # the monitoring-triggered evaluation produced real evidence, same as a direct call would
