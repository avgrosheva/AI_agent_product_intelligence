"""Stage 5 task 1/7: the generic, domain-parametrized API
(/api/v1/domains/{domain}/...) proven against BOTH domains through the
same endpoints — no per-domain branching in the router, no commerce
default. Commerce uses the dev-scale fixture data conftest.py already
loads; support ingests its own small fixture through the Stage 3 ingestion
API, exactly like tests/test_support_domain_adapter.py."""

from __future__ import annotations

CATEGORIES = ["billing", "technical", "account_access", "shipping_status", "general_inquiry"]


def _support_payload(domain: str, tag: str) -> dict:
    def session(sid: str, version: str, outcome: str) -> dict:
        return {
            "external_session_id": sid,
            "external_experiment_id": f"generic-api-exp-{tag}",
            "agent_version": version,
            "external_user_id": f"user-{sid}",
            "started_at": "2026-03-01T00:00:00",
            "ended_at": "2026-03-01T00:05:00",
            "messages": [{"external_message_id": f"{sid}-m0", "turn_index": 0, "sender": "user", "text": "help", "created_at": "2026-03-01T00:00:00"}],
            "actions": [{"external_action_id": f"{sid}-a0", "sequence_index": 0, "action_type": "triage_ticket", "started_at": "2026-03-01T00:00:01", "tool_calls": []}],
            "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
            "context": {"ticket_category": "billing"},
        }

    sessions = []
    for i in range(12):
        sessions.append(session(f"api-{tag}-v1-{i}", "v1", "resolved" if i % 3 else "escalated"))
    for i in range(12):
        sessions.append(session(f"api-{tag}-v2-{i}", "v2", "resolved"))
    return {
        "domain": domain,
        "experiments": [{"external_experiment_id": f"generic-api-exp-{tag}", "name": f"Generic API Test {tag}", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": sessions,
    }


def _ingest_support_fixture(api_client, tag: str, support_project_id: str) -> str:
    from backend.domains.support.adapter import SupportAdapter

    resp = api_client.post("/api/v1/ingest/sessions", json=_support_payload(SupportAdapter.domain, tag), params={"project_id": support_project_id})
    assert resp.status_code == 201
    experiments = api_client.get("/api/v1/domains/support/experiments").json()["experiments"]
    exp = next(e for e in experiments if e["name"] == f"Generic API Test {tag}")
    return exp["experiment_id"]


def test_list_domains_includes_both(api_client):
    resp = api_client.get("/api/v1/domains")
    assert resp.status_code == 200
    assert set(resp.json()) == {"commerce", "support"}


def test_unknown_domain_is_404(api_client):
    resp = api_client.get("/api/v1/domains/nonexistent/experiments")
    assert resp.status_code == 404


def test_generic_experiments_endpoint_on_commerce(api_client, experiment_id):
    resp = api_client.get("/api/v1/domains/commerce/experiments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "commerce"
    assert any(e["experiment_id"] == experiment_id for e in body["experiments"])


def test_generic_experiments_endpoint_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "list", support_project_id)
    resp = api_client.get("/api/v1/domains/support/experiments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "support"
    assert any(e["experiment_id"] == exp_id for e in body["experiments"])


def test_generic_metrics_endpoint_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/metrics")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    assert any(m["metric_name"] == "conversion_rate" for m in metrics)


def test_generic_metrics_endpoint_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "metrics", support_project_id)
    resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/metrics")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    names = {m["metric_name"] for m in metrics}
    assert "resolution_rate" in names
    # ticket_category is pre_treatment/non-inferential -> never in this table
    assert "ticket_category" not in names


def test_generic_guardrails_endpoint_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/guardrails")
    assert resp.status_code == 200
    body = resp.json()
    assert {c["name"] for c in body["checks"]} == {"p95_latency", "tool_error_rate", "cost_per_session"}


def test_generic_guardrails_endpoint_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "guardrails", support_project_id)
    resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/guardrails")
    assert resp.status_code == 200
    body = resp.json()
    assert {c["name"] for c in body["checks"]} == {"escalation_rate_guardrail"}
    assert body["checks"][0]["metric"] == "escalation_rate"


def test_generic_investigation_requires_primary_metric_query_param(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/investigation")
    assert resp.status_code == 422


def test_generic_investigation_rejects_unknown_metric(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/investigation?primary_metric=not_a_real_metric")
    assert resp.status_code == 422


def test_generic_investigation_endpoint_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/investigation?primary_metric=abandonment_rate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation"]["verdict"] in {"ship", "hold", "roll_back"}
    assert body["primary_metric"] == "abandonment_rate"


def test_generic_investigation_endpoint_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "investigation", support_project_id)
    resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/investigation?primary_metric=resolution_rate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation"]["verdict"] in {"ship", "hold", "roll_back"}
    # zero registered mechanisms -> every finding has no dominant failure mode
    for finding in body["findings"]:
        assert finding["dominant_failure_mode"] is None


def test_generic_mechanisms_endpoint_on_commerce(api_client):
    resp = api_client.get("/api/v1/domains/commerce/mechanisms")
    assert resp.status_code == 200
    names = {m["name"] for m in resp.json()["mechanisms"]}
    assert "retrieval_failure" in names and "unnecessary_clarification" in names


def test_generic_mechanisms_endpoint_on_support_is_empty():
    from backend.domains.support.mechanisms import SUPPORT_MECHANISMS

    assert SUPPORT_MECHANISMS.all_names == ()


def test_generic_sessions_list_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "commerce"
    assert len(body["items"]) == 5
    assert body["items"][0]["agent_version"] in ("v1", "v2")


def test_generic_sessions_list_and_detail_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "sessions", support_project_id)
    # Scoped to this test's own experiment: other tests sharing the same
    # support_project_id (one project per domain, by design) also ingest
    # sessions there, and an unscoped list spans every experiment in the
    # project — sorted by started_at, so a differently-dated fixture from
    # another test could otherwise land in this page instead of this
    # test's own "triage_ticket" sessions.
    resp = api_client.get(f"/api/v1/domains/support/sessions?experiment_id={exp_id}&limit=3")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 3
    sid = body["items"][0]["session_id"]

    detail = api_client.get(f"/api/v1/domains/support/sessions/{sid}")
    assert detail.status_code == 200
    d = detail.json()
    assert d["domain"] == "support"
    assert d["action_sequence"] == ["triage_ticket"]


def test_generic_session_detail_404_for_unknown_id(api_client):
    resp = api_client.get("/api/v1/domains/support/sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
