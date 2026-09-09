"""Stage 5 tasks 2-4/6/7: release monitoring — evaluate on demand,
persist the result, expose the latest status, and prove the decision is
deterministic (same data -> same status every time) for both domains.
Also proves support => SHIP and commerce => HOLD are unchanged by this
stage (task 6)."""

from __future__ import annotations


def _ingest_support_release_fixture(api_client, tag: str, support_project_id: str) -> str:
    from backend.domains.support.adapter import SupportAdapter

    def session(sid: str, version: str, category: str, outcome: str, handle_time: float, csat) -> dict:
        outcome_metrics = [{"name": "csat_score", "value": csat}] if csat is not None else []
        return {
            "external_session_id": sid,
            "external_experiment_id": f"release-exp-{tag}",
            "agent_version": version,
            "external_user_id": f"user-{sid}",
            "started_at": "2026-04-01T00:00:00",
            "ended_at": "2026-04-01T00:05:00",
            "messages": [{"external_message_id": f"{sid}-m0", "turn_index": 0, "sender": "user", "text": "help", "created_at": "2026-04-01T00:00:00"}],
            "actions": [{"external_action_id": f"{sid}-a0", "sequence_index": 0, "action_type": "triage_ticket", "started_at": "2026-04-01T00:00:01", "tool_calls": []}],
            "outcome": {"label": outcome, "metrics": outcome_metrics},
            "metrics": [{"name": "handle_time_seconds", "value": handle_time}],
            "context": {"ticket_category": category},
        }

    # Deterministic (no RNG, so this test is never flaky) but large enough
    # (n=40/arm) and strong enough an effect (60%->90% resolution, with
    # escalation DECREASING so the guardrail — which only fires on an
    # escalation-rate INCREASE — stays safe) to reliably clear both the
    # minimum-sample and statistical-significance gates, mirroring
    # scripts/generate_support_fixture.py's real, larger-scale proof.
    sessions = []
    for i in range(40):
        if i % 10 < 6:
            outcome, csat = "resolved", 3.8
        elif i % 10 < 9:
            outcome, csat = "escalated", None
        else:
            outcome, csat = "abandoned", None
        sessions.append(session(f"rel-{tag}-v1-{i}", "v1", "billing", outcome, 420.0, csat))
    for i in range(40):
        if i % 10 < 9:
            outcome, csat = "resolved", 4.4
        else:
            outcome, csat = "escalated", None
        sessions.append(session(f"rel-{tag}-v2-{i}", "v2", "billing", outcome, 260.0, csat))

    payload = {
        "domain": SupportAdapter.domain,
        "experiments": [{"external_experiment_id": f"release-exp-{tag}", "name": f"Release Test {tag}", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": sessions,
    }
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": support_project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]
    exp = next(e for e in experiments if e["name"] == f"Release Test {tag}")
    return exp["experiment_id"]


def test_support_release_evaluation_ships(api_client, support_project_id):
    """Stage 5 task 6: support's planted resolution-rate improvement with
    a guardrail-safe escalation trade-off still resolves to SHIP, unchanged
    by adding release persistence around the same Investigation engine."""
    exp_id = _ingest_support_release_fixture(api_client, "ship", support_project_id)
    resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    assert resp.status_code == 201
    body = resp.json()
    assert body["domain"] == "support"
    assert body["experiment_id"] == exp_id
    assert body["primary_metric"] == "resolution_rate"
    assert body["status"] == "SHIP"
    assert body["any_guardrail_breach"] is False
    assert "resolution_rate" in body["key_metrics"]
    assert body["breached_guardrails"] == []


def test_commerce_release_evaluation_holds(api_client, experiment_id):
    """Stage 5 task 6: commerce's documented abandonment-lens finding
    (p95_latency guardrail breach) still resolves to HOLD."""
    resp = api_client.post(f"/api/v1/domains/commerce/experiments/{experiment_id}/release-evaluations?primary_metric=abandonment_rate")
    assert resp.status_code == 201
    body = resp.json()
    assert body["domain"] == "commerce"
    assert body["status"] == "HOLD"


def test_release_evaluation_is_persisted_and_status_matches(api_client, support_project_id):
    exp_id = _ingest_support_release_fixture(api_client, "persist", support_project_id)
    create_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    assert create_resp.status_code == 201
    created = create_resp.json()

    status_resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-status?project_id={support_project_id}")
    assert status_resp.status_code == 200
    latest = status_resp.json()
    assert latest["evaluation_id"] == created["evaluation_id"]
    assert latest["status"] == created["status"]


def test_release_history_accumulates_across_calls(api_client, support_project_id):
    exp_id = _ingest_support_release_fixture(api_client, "history", support_project_id)
    for _ in range(3):
        resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
        assert resp.status_code == 201

    history_resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-history?project_id={support_project_id}")
    assert history_resp.status_code == 200
    evaluations = history_resp.json()["evaluations"]
    assert len(evaluations) >= 3
    # newest first
    timestamps = [e["evaluated_at"] for e in evaluations]
    assert timestamps == sorted(timestamps, reverse=True)


def test_release_status_404_before_any_evaluation(api_client, support_project_id):
    exp_id = _ingest_support_release_fixture(api_client, "no_eval_yet", support_project_id)
    resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-status?project_id={support_project_id}")
    assert resp.status_code == 404


def test_release_evaluation_decision_is_deterministic(api_client, support_project_id):
    """Same data evaluated twice must produce the exact same status and
    the same set of breached guardrails — no randomness in the decision
    itself (the underlying stats already guarantee this; this test proves
    the release-monitoring wrapper doesn't introduce any)."""
    exp_id = _ingest_support_release_fixture(api_client, "deterministic", support_project_id)
    first = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}").json()
    second = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}").json()

    assert first["status"] == second["status"]
    assert first["any_guardrail_breach"] == second["any_guardrail_breach"]
    assert first["breached_guardrails"] == second["breached_guardrails"]
    assert first["key_metrics"] == second["key_metrics"]
    assert first["evaluation_id"] != second["evaluation_id"]  # still two distinct history rows


def test_release_evaluation_404_for_unknown_experiment(api_client, support_project_id):
    resp = api_client.post(f"/api/v1/domains/support/experiments/nonexistent-exp/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    assert resp.status_code == 404


def test_release_evaluation_422_for_unknown_metric(api_client, support_project_id):
    exp_id = _ingest_support_release_fixture(api_client, "bad_metric", support_project_id)
    resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=not_a_metric&project_id={support_project_id}")
    assert resp.status_code == 422


def test_release_and_generic_router_packages_never_import_commerce_or_support_domain():
    """Stage 5 task 7: backend.release (service code) and
    backend.app.routers.domains (the generic router) must never import
    backend.domains.commerce or backend.domains.support directly — only
    backend.app.domain_registry (the composition root) is allowed to."""
    import ast
    import importlib
    import inspect
    import pkgutil

    import backend.release
    import backend.app.routers.domains as domains_router

    forbidden = ("backend.domains.commerce", "backend.domains.support")

    modules = [domains_router]
    for _, name, _ in pkgutil.walk_packages(backend.release.__path__, prefix="backend.release."):
        modules.append(importlib.import_module(name))

    for module in modules:
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for prefix in forbidden:
                    assert not node.module.startswith(prefix), f"{module.__name__} imports from {node.module}, forbidden prefix {prefix!r}"
