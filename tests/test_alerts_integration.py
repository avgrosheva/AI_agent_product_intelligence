"""Stage 6 tasks 1-2/7: alerts actually get created (and deduplicated) as
a side effect of a real release evaluation, and can be listed/acknowledged
through the API. Uses a deterministic, large-effect support-domain
fixture (regression, not improvement) to reliably reach ROLLBACK without
depending on real statistical variance — the rule logic itself is unit
tested against synthetic fields in tests/test_alert_rules.py."""

from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module", autouse=True)
def _clean_alerts_table(db_engine):
    """The `alerts` table has no FK to `sessions` (deliberately, to stay
    domain-agnostic — see backend/alerts/models.py) so it is NOT wiped by
    conftest.py's dev-dataset truncate-and-reload, unlike commerce's own
    tables. Without this, exact-count assertions below would accumulate
    leftover rows across separate `pytest` invocations against the same
    persistent test database."""
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM alerts"))
    yield


def _ingest_rollback_fixture(api_client, tag: str, support_project_id: str) -> str:
    from backend.domains.support.adapter import SupportAdapter

    def session(sid: str, version: str, outcome: str) -> dict:
        return {
            "external_session_id": sid,
            "external_experiment_id": f"alert-exp-{tag}",
            "agent_version": version,
            "external_user_id": f"user-{sid}",
            "started_at": "2026-05-01T00:00:00",
            "ended_at": "2026-05-01T00:05:00",
            "messages": [{"external_message_id": f"{sid}-m0", "turn_index": 0, "sender": "user", "text": "help", "created_at": "2026-05-01T00:00:00"}],
            "actions": [{"external_action_id": f"{sid}-a0", "sequence_index": 0, "action_type": "triage_ticket", "started_at": "2026-05-01T00:00:01", "tool_calls": []}],
            "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
            "context": {"ticket_category": "billing"},
        }

    # v1 resolves 90% of the time, v2 only 60% -- a large, reliable
    # regression (ROLLBACK), n=40/arm so it also clears the minimum-sample
    # gates without depending on random variance.
    sessions = []
    for i in range(40):
        sessions.append(session(f"alert-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 9 else "escalated"))
    for i in range(40):
        sessions.append(session(f"alert-{tag}-v2-{i}", "v2", "resolved" if i % 10 < 6 else "escalated"))

    payload = {
        "domain": SupportAdapter.domain,
        "experiments": [{"external_experiment_id": f"alert-exp-{tag}", "name": f"Alert Test {tag}", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": sessions,
    }
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": support_project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]
    exp = next(e for e in experiments if e["name"] == f"Alert Test {tag}")
    return exp["experiment_id"]


def test_rollback_evaluation_creates_a_critical_alert(api_client, support_project_id):
    exp_id = _ingest_rollback_fixture(api_client, "create", support_project_id)
    eval_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    assert eval_resp.status_code == 201
    assert eval_resp.json()["status"] == "ROLLBACK"

    alerts_resp = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={support_project_id}")
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()["alerts"]
    rollback_alerts = [a for a in alerts if a["rule"] == "rollback"]
    assert len(rollback_alerts) == 1
    assert rollback_alerts[0]["severity"] == "critical"
    assert rollback_alerts[0]["status"] == "open"
    assert rollback_alerts[0]["acknowledged_at"] is None


def test_repeated_evaluation_does_not_duplicate_open_alerts(api_client, support_project_id):
    exp_id = _ingest_rollback_fixture(api_client, "dedup", support_project_id)
    for _ in range(3):
        resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
        assert resp.status_code == 201

    alerts = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={support_project_id}").json()["alerts"]
    rollback_alerts = [a for a in alerts if a["rule"] == "rollback"]
    assert len(rollback_alerts) == 1  # not 3


def test_acknowledging_an_alert_allows_a_new_one_after_the_next_evaluation(api_client, support_project_id):
    exp_id = _ingest_rollback_fixture(api_client, "reopen", support_project_id)
    api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    alerts = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={support_project_id}").json()["alerts"]
    rollback_alert = next(a for a in alerts if a["rule"] == "rollback")

    ack_resp = api_client.post(f"/api/v1/alerts/{rollback_alert['alert_id']}/acknowledge")
    assert ack_resp.status_code == 200
    acked = ack_resp.json()
    assert acked["status"] == "acknowledged"
    assert acked["acknowledged_at"] is not None

    # The still-broken experiment gets evaluated again -> a NEW alert,
    # since the old one is no longer "open".
    api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    alerts_after = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={support_project_id}").json()["alerts"]
    rollback_alerts_after = [a for a in alerts_after if a["rule"] == "rollback"]
    assert len(rollback_alerts_after) == 2
    assert sum(1 for a in rollback_alerts_after if a["status"] == "open") == 1
    assert sum(1 for a in rollback_alerts_after if a["status"] == "acknowledged") == 1


def test_acknowledge_unknown_alert_is_404(api_client):
    resp = api_client.post("/api/v1/alerts/00000000-0000-0000-0000-000000000000/acknowledge")
    assert resp.status_code == 404


def test_alerts_filterable_by_severity_and_status(api_client, support_project_id):
    exp_id = _ingest_rollback_fixture(api_client, "filter", support_project_id)
    api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")

    critical = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={support_project_id}&severity=critical").json()["alerts"]
    assert all(a["severity"] == "critical" for a in critical)
    assert len(critical) >= 1

    open_only = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={support_project_id}&status=open").json()["alerts"]
    assert all(a["status"] == "open" for a in open_only)


def test_alerts_list_paginates_with_stable_ordering_and_metadata(api_client, support_project_id):
    """Stage 17 task 7: alerts accumulate indefinitely across every
    scheduled monitoring run and manual evaluation project-wide, so a bare
    `limit` (the original signature) could only ever show the newest
    page. Two more rollback experiments here each add at least one more
    open, critical alert (on top of whatever earlier tests in this module
    already created for this same support domain) -- proves total/limit/
    offset are reported and that limit=1 pages (newest first) land on the
    exact same alerts, in the exact same order, as one unpaginated call."""
    exp_a = _ingest_rollback_fixture(api_client, "page_a", support_project_id)
    exp_b = _ingest_rollback_fixture(api_client, "page_b", support_project_id)
    api_client.post(f"/api/v1/domains/support/experiments/{exp_a}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    api_client.post(f"/api/v1/domains/support/experiments/{exp_b}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")

    full = api_client.get(f"/api/v1/alerts?domain=support&project_id={support_project_id}&limit=200").json()
    scoped_experiment_ids = {a["experiment_id"] for a in full["alerts"]} & {exp_a, exp_b}
    assert scoped_experiment_ids == {exp_a, exp_b}
    assert full["limit"] == 200 and full["offset"] == 0
    assert full["total"] == len(full["alerts"])  # under the 200-row cap, nothing left off this page

    page1 = api_client.get(f"/api/v1/alerts?domain=support&project_id={support_project_id}&limit=1&offset=0").json()
    page2 = api_client.get(f"/api/v1/alerts?domain=support&project_id={support_project_id}&limit=1&offset=1").json()
    assert page1["total"] == full["total"] == page2["total"]
    assert len(page1["alerts"]) == 1 and len(page2["alerts"]) == 1
    assert page1["alerts"][0]["alert_id"] != page2["alerts"][0]["alert_id"]
    assert page1["alerts"][0]["alert_id"] == full["alerts"][0]["alert_id"]
    assert page2["alerts"][0]["alert_id"] == full["alerts"][1]["alert_id"]


def test_commerce_release_evaluation_also_flows_through_alerts(api_client, experiment_id, commerce_project_id):
    """Compatibility (task 7): the same alert pipeline works for commerce,
    not just support — whatever verdict the dev-scale dataset produces,
    the call must not error, and any resulting alert must carry
    domain='commerce'."""
    resp = api_client.post(f"/api/v1/domains/commerce/experiments/{experiment_id}/release-evaluations?primary_metric=abandonment_rate")
    assert resp.status_code == 201
    alerts = api_client.get(f"/api/v1/alerts?domain=commerce&experiment_id={experiment_id}&project_id={commerce_project_id}").json()["alerts"]
    assert all(a["domain"] == "commerce" for a in alerts)


def test_alerts_and_review_router_packages_never_import_commerce_or_support_domain():
    """Stage 6 task 7 (extends Stage 5's isolation guarantee): backend.alerts,
    backend.review, and their routers must never import backend.domains.commerce
    or backend.domains.support directly."""
    import ast
    import importlib
    import inspect
    import pkgutil

    import backend.alerts
    import backend.review
    import backend.app.routers.alerts as alerts_router
    import backend.app.routers.review as review_router

    forbidden = ("backend.domains.commerce", "backend.domains.support")
    modules = [alerts_router, review_router]
    for pkg in (backend.alerts, backend.review):
        for _, name, _ in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg.__name__}."):
            modules.append(importlib.import_module(name))

    for module in modules:
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for prefix in forbidden:
                    assert not node.module.startswith(prefix), f"{module.__name__} imports from {node.module}, forbidden prefix {prefix!r}"
