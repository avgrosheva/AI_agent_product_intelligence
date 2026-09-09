"""Stage 11 task 6: critical data quality must gate a confident SHIP.
Uses a deliberately metric-free fixture (100% missing metric coverage,
tripping the "critical" threshold — backend.quality.service) alongside a
real, statistically clean SHIP-worthy improvement, and proves the
release-evaluation response reflects the gate rather than a plain SHIP."""

from __future__ import annotations

import uuid

from tests._connector_test_helpers import new_support_project


def _ingest_ship_fixture_with_no_metrics(api_client, project_id: str, tag: str) -> str:
    def session(sid: str, version: str, outcome: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"gate-exp-{tag}", "agent_version": version, "external_user_id": f"user-{sid}",
            "started_at": "2026-09-01T00:00:00", "outcome": {"label": outcome, "metrics": []}, "metrics": [],
        }

    # v1 60% resolved, v2 90% resolved -- the same reliable, large SHIP-
    # worthy improvement tests/test_release_monitoring.py's own fixture
    # uses, but with NO metrics ingested for any session at all.
    sessions = [session(f"gate-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 6 else "escalated") for i in range(40)]
    sessions += [session(f"gate-{tag}-v2-{i}", "v2", "resolved" if i % 10 < 9 else "escalated") for i in range(40)]
    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"gate-exp-{tag}", "name": f"Gating Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    return next(e["experiment_id"] for e in experiments if e["name"] == f"Gating Test {tag}")


def test_critical_data_quality_downgrades_ship_to_hold(api_client, test_identity):
    tag = f"gate-{uuid.uuid4().hex[:8]}"
    # A dedicated, throwaway project so this test's own 100%-missing-metric
    # fixture is the ONLY data quality signal in play -- never shares a
    # project with another test's own (healthy) fixture data.
    project_id = new_support_project(test_identity, "Data Quality Gating Project")
    exp_id = _ingest_ship_fixture_with_no_metrics(api_client, project_id, tag)

    quality = api_client.get(f"/api/v1/domains/support/data-quality?project_id={project_id}")
    assert quality.status_code == 200
    assert quality.json()["status"] == "critical"

    eval_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={project_id}")
    assert eval_resp.status_code == 201
    body = eval_resp.json()

    assert body["raw_status"] == "SHIP"  # the Investigation engine's own verdict is still honestly recorded
    assert body["status"] == "HOLD"  # but never presented as a confident SHIP under critical data quality
    assert body["data_quality_status"] == "critical"
    assert body["data_quality_gated"] is True
    assert "data quality is critical" in body["primary_reason"]


def test_healthy_data_quality_never_gates_ship(api_client, test_identity):
    tag = f"nogate-{uuid.uuid4().hex[:8]}"
    project_id = new_support_project(test_identity, "Data Quality No-Gate Project")

    def session(sid: str, version: str, outcome: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"nogate-exp-{tag}", "agent_version": version, "external_user_id": f"user-{sid}",
            "started_at": "2026-09-01T00:00:00", "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
        }

    sessions = [session(f"nogate-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 6 else "escalated") for i in range(40)]
    sessions += [session(f"nogate-{tag}-v2-{i}", "v2", "resolved" if i % 10 < 9 else "escalated") for i in range(40)]
    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"nogate-exp-{tag}", "name": f"No Gate Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    exp_id = next(e["experiment_id"] for e in api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"] if e["name"] == f"No Gate Test {tag}")

    quality = api_client.get(f"/api/v1/domains/support/data-quality?project_id={project_id}")
    assert quality.json()["status"] == "healthy"

    eval_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={project_id}")
    body = eval_resp.json()
    assert body["status"] == "SHIP"
    assert body["raw_status"] == "SHIP"
    assert body["data_quality_gated"] is False


def test_commerce_release_evaluation_unaffected_by_data_quality_gating(api_client, experiment_id):
    """Stage 11 task 8: commerce's own dataset lives outside the generic
    ingestion tables (Stage 8) -- its data-quality report always shows
    "healthy/not_applicable" (nothing ingested there), so commerce's
    long-standing HOLD verdict must be completely unaffected."""
    resp = api_client.post(f"/api/v1/domains/commerce/experiments/{experiment_id}/release-evaluations?primary_metric=abandonment_rate")
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "HOLD"
    assert body["raw_status"] == "HOLD"
    assert body["data_quality_gated"] is False
