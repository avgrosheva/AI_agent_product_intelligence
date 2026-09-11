"""Stage 18 task 7/11: the read-only operational health endpoint. Uses
api_client (test_identity's admin) since this endpoint is deliberately
NOT project-scoped -- any authenticated user reads the same deployment-
wide signal."""

from __future__ import annotations


def test_health_requires_authentication(commerce_project_id):
    from fastapi.testclient import TestClient

    from backend.app.main import app

    resp = TestClient(app).get("/api/v1/ops/health")
    assert resp.status_code == 401


def test_health_reports_database_scheduler_cache_and_connector_state(api_client):
    resp = api_client.get("/api/v1/ops/health")
    assert resp.status_code == 200
    body = resp.json()

    assert body["database"]["connected"] is True
    assert body["database"]["error"] is None

    assert isinstance(body["scheduler"]["enabled_via_env"], bool)
    assert isinstance(body["scheduler"]["lease_held"], bool)

    # Connector "availability" is booleans only -- structurally, no
    # credential value could ever appear here regardless of what's set in
    # this environment.
    assert isinstance(body["connectors"]["langfuse_configured"], bool)
    assert isinstance(body["connectors"]["postgres_business_configured"], bool)

    assert body["cache"]["metrics_table_cache_size"] >= 0
    assert body["cache"]["metrics_table_cache_size"] <= body["cache"]["metrics_table_cache_maxsize"]
    assert body["cache"]["investigation_cache_size"] >= 0
    assert body["cache"]["investigation_cache_size"] <= body["cache"]["investigation_cache_maxsize"]

    # latest_monitoring_run, when present, must never identify WHOSE data
    # it touched -- only status/timing, so one tenant's health check can
    # never surface another tenant's project/experiment id.
    if body["latest_monitoring_run"] is not None:
        assert set(body["latest_monitoring_run"].keys()) == {"status", "started_at", "completed_at"}


def test_health_reflects_a_currently_held_scheduler_lease(api_client, db_engine):
    from backend.monitoring.lease import try_acquire_or_renew_lease
    from backend.monitoring.scheduler import SCHEDULER_LEASE_KEY

    assert try_acquire_or_renew_lease(db_engine, SCHEDULER_LEASE_KEY, "test-holder", ttl_seconds=60) is True

    resp = api_client.get("/api/v1/ops/health")
    body = resp.json()
    assert body["scheduler"]["lease_held"] is True
    assert body["scheduler"]["holder_id"] == "test-holder"
