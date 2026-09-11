"""Stage 12 tasks 4-7/9: the project-config and onboarding-status API,
end to end through the real routes — validation errors, persisted
config actually overriding a domain's static defaults (proven by
observing the generic guardrails/metrics/investigation endpoints change
behavior), onboarding readiness, and tenant isolation."""

from __future__ import annotations

import uuid

from tests._connector_test_helpers import new_support_project


def test_get_config_before_any_save_is_an_empty_shell(api_client, support_project_id):
    resp = api_client.get(f"/api/v1/domains/support/config?project_id={support_project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["primary_metric"] is None
    assert body["enabled_notification_rules"] == []


def test_put_config_persists_and_get_reflects_it(api_client, test_identity):
    project_id = new_support_project(test_identity, "Config Persist Project")
    body = {"primary_metric": "resolution_rate", "monitoring_cadence_seconds": 1800, "enabled_notification_rules": ["ROLLBACK", "HOLD"]}
    put_resp = api_client.put(f"/api/v1/domains/support/config?project_id={project_id}", json=body)
    assert put_resp.status_code == 200
    assert put_resp.json()["primary_metric"] == "resolution_rate"
    assert put_resp.json()["monitoring_cadence_seconds"] == 1800

    get_resp = api_client.get(f"/api/v1/domains/support/config?project_id={project_id}")
    assert get_resp.json()["primary_metric"] == "resolution_rate"
    assert sorted(get_resp.json()["enabled_notification_rules"]) == ["HOLD", "ROLLBACK"]


def test_put_config_rejects_unknown_notification_event_type(api_client, test_identity):
    project_id = new_support_project(test_identity, "Config Bad Rule Project")
    resp = api_client.put(f"/api/v1/domains/support/config?project_id={project_id}", json={"enabled_notification_rules": ["NOT_A_REAL_EVENT"]})
    assert resp.status_code == 422


def test_put_config_rejects_guardrail_referencing_unknown_metric(api_client, test_identity):
    project_id = new_support_project(test_identity, "Config Bad Guardrail Project")
    body = {
        "metrics": {"metrics": [{"name": "resolution_rate", "value_column": "resolved"}]},
        "guardrails": {"guardrails": [{"name": "g1", "metric": "totally_unknown", "column": "x", "aggregation": "cluster_mean", "threshold": 0.1}]},
    }
    resp = api_client.put(f"/api/v1/domains/support/config?project_id={project_id}", json=body)
    assert resp.status_code == 422
    assert "totally_unknown" in resp.json()["detail"]


def test_put_config_rejects_primary_metric_not_in_configured_metrics(api_client, test_identity):
    project_id = new_support_project(test_identity, "Config Bad Primary Metric Project")
    body = {"primary_metric": "nonexistent", "metrics": {"metrics": [{"name": "resolution_rate", "value_column": "resolved"}]}}
    resp = api_client.put(f"/api/v1/domains/support/config?project_id={project_id}", json=body)
    assert resp.status_code == 422


def test_persisted_guardrails_override_static_defaults(api_client, test_identity):
    """Stage 12 tasks 4/7: a project's own persisted guardrail config
    actually changes what the generic guardrails endpoint returns,
    proving the DomainAdapter override wiring (not just that the config
    row exists)."""
    project_id = new_support_project(test_identity, "Config Guardrail Override Project")
    tag = f"override-{uuid.uuid4().hex[:8]}"
    sessions = [
        {
            "external_session_id": f"cfg-{tag}-{i}", "external_experiment_id": f"cfg-exp-{tag}", "agent_version": "v1" if i < 20 else "v2",
            "external_user_id": f"user-{i}", "started_at": "2026-09-01T00:00:00", "outcome": {"label": "resolved", "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 100.0}],
        }
        for i in range(40)
    ]
    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"cfg-exp-{tag}", "name": f"Config Override {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    ingest_resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert ingest_resp.status_code == 201

    custom_guardrails = {
        "guardrails": [
            {"name": "custom_handle_time_guardrail", "metric": "resolution_rate", "column": "handle_time_seconds", "aggregation": "cluster_mean", "kind": "absolute", "direction": "increase_is_bad", "threshold": 1.0, "severity": "warning", "enabled": True}
        ]
    }
    put_resp = api_client.put(f"/api/v1/domains/support/config?project_id={project_id}", json={"guardrails": custom_guardrails})
    assert put_resp.status_code == 200

    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    exp_id = next(e["experiment_id"] for e in experiments if e["name"] == f"Config Override {tag}")

    guardrails_resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/guardrails?project_id={project_id}")
    assert guardrails_resp.status_code == 200
    names = {c["name"] for c in guardrails_resp.json()["checks"]}
    assert names == {"custom_handle_time_guardrail"}  # the static "escalation_rate_guardrail" is gone -- fully replaced


def test_config_is_project_scoped(api_client, support_project_id, test_identity):
    other_project_id = new_support_project(test_identity, "Config Isolation Project")
    api_client.put(f"/api/v1/domains/support/config?project_id={support_project_id}", json={"primary_metric": "resolution_rate"})

    other = api_client.get(f"/api/v1/domains/support/config?project_id={other_project_id}")
    assert other.json()["primary_metric"] is None  # never leaked from another project


def test_onboarding_status_reflects_real_state(api_client, test_identity):
    project_id = new_support_project(test_identity, "Onboarding Status Project")
    status = api_client.get(f"/api/v1/domains/support/onboarding-status?project_id={project_id}").json()
    assert status["ingestion_connected"] is True
    assert status["data_received"] is False
    assert status["primary_metric_configured"] is False
    assert status["guardrails_configured"] is True  # support's own static guardrail is in effect
    assert status["data_quality_status"] == "healthy"
    assert status["monitoring_enabled"] is False
    assert status["notifications_configured"] is False

    api_client.put(f"/api/v1/domains/support/config?project_id={project_id}", json={"primary_metric": "resolution_rate"})
    status_after = api_client.get(f"/api/v1/domains/support/onboarding-status?project_id={project_id}").json()
    assert status_after["primary_metric_configured"] is True


def test_onboarding_status_is_project_scoped(api_client, support_project_id, test_identity):
    other_project_id = new_support_project(test_identity, "Onboarding Isolation Project")
    api_client.put(f"/api/v1/domains/support/config?project_id={support_project_id}", json={"primary_metric": "resolution_rate"})

    other_status = api_client.get(f"/api/v1/domains/support/onboarding-status?project_id={other_project_id}").json()
    assert other_status["primary_metric_configured"] is False


def test_config_response_exposes_available_metrics_and_guardrails(api_client, test_identity):
    """Stage 15 tasks 3-5: the config endpoint's response projects the
    domain's currently-effective metrics/guardrails/context fields, so
    the onboarding UI can render dropdowns/checklists instead of asking
    a PM to hand-write JSON. Static defaults show up before any config
    is ever saved."""
    project_id = new_support_project(test_identity, "Available Options Project")
    body = api_client.get(f"/api/v1/domains/support/config?project_id={project_id}").json()

    metric_names = {m["name"] for m in body["available_metrics"]}
    assert "resolution_rate" in metric_names
    resolution = next(m for m in body["available_metrics"] if m["name"] == "resolution_rate")
    assert resolution["direction"] in {"higher_is_better", "lower_is_better"}
    assert isinstance(resolution["is_inferential"], bool)
    assert "value_column" in resolution  # present (possibly null) so the UI can round-trip custom metrics safely

    guardrail_names = {g["name"] for g in body["available_guardrails"]}
    assert guardrail_names == {"escalation_rate_guardrail"}  # support's static default

    assert body["available_context_fields"] == []  # no sessions ingested yet


def test_config_response_available_guardrails_reflect_persisted_override(api_client, test_identity):
    """A saved guardrail override changes not just the generic guardrails
    endpoint (already covered) but also the config response's own
    available_guardrails projection, so the onboarding UI reflects what
    is actually in effect right after a save."""
    project_id = new_support_project(test_identity, "Available Guardrails Override Project")
    custom_guardrails = {
        "guardrails": [
            {"name": "custom_g", "metric": "resolution_rate", "column": "handle_time_seconds", "aggregation": "cluster_mean", "kind": "absolute", "direction": "increase_is_bad", "threshold": 1.0, "severity": "warning", "enabled": True}
        ]
    }
    put_resp = api_client.put(f"/api/v1/domains/support/config?project_id={project_id}", json={"guardrails": custom_guardrails})
    assert put_resp.status_code == 200
    assert {g["name"] for g in put_resp.json()["available_guardrails"]} == {"custom_g"}

    get_resp = api_client.get(f"/api/v1/domains/support/config?project_id={project_id}")
    assert {g["name"] for g in get_resp.json()["available_guardrails"]} == {"custom_g"}


def test_config_response_available_context_fields_reflect_ingested_data(api_client, test_identity):
    """available_context_fields must come from real ingested session
    context keys (backend.project_config.service.existing_context_keys),
    not a static list -- so segment setup never lets a PM select a field
    that doesn't actually exist in this project's data."""
    project_id = new_support_project(test_identity, "Available Context Fields Project")
    tag = f"ctx-{uuid.uuid4().hex[:8]}"
    sessions = [
        {
            "external_session_id": f"{tag}-{i}", "external_experiment_id": f"{tag}-exp", "agent_version": "v1" if i < 5 else "v2",
            "external_user_id": f"user-{i}", "started_at": "2026-09-01T00:00:00", "outcome": {"label": "resolved", "metrics": []},
            "metrics": [], "context": {"ticket_category": "billing"},
        }
        for i in range(10)
    ]
    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"{tag}-exp", "name": f"Context Fields {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    ingest_resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert ingest_resp.status_code == 201

    body = api_client.get(f"/api/v1/domains/support/config?project_id={project_id}").json()
    assert "ticket_category" in body["available_context_fields"]
