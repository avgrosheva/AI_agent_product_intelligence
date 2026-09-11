"""Stage 12 task 9: full end-to-end regression — a project configures
itself entirely through the API (primary metric default, notification
rule, a webhook channel), ingests data, and a release evaluation that
never even names a primary_metric in the request still reaches the
right verdict, fires an alert, AND delivers a real (fake-transport)
webhook notification, all visible in the delivery log and the
onboarding-status endpoint."""

from __future__ import annotations

import uuid

from tests._connector_test_helpers import new_support_project

OTHER_CATEGORIES = ["technical", "account_access", "shipping_status", "general_inquiry"]


def _ingest_rollback_fixture(api_client, project_id: str, tag: str) -> str:
    def session(sid: str, version: str, outcome: str, category: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"cfg12-exp-{tag}", "agent_version": version,
            "external_user_id": f"user-{sid}", "started_at": "2026-09-01T00:00:00", "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}], "context": {"ticket_category": category},
        }

    sessions = []
    for i in range(40):
        category = "billing" if i < 20 else OTHER_CATEGORIES[i % 4]
        sessions.append(session(f"cfg12-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 9 else "escalated", category))
    for i in range(40):
        category = "billing" if i < 20 else OTHER_CATEGORIES[i % 4]
        outcome = ("resolved" if i % 10 < 2 else "escalated") if category == "billing" else ("resolved" if i % 10 < 8 else "escalated")
        sessions.append(session(f"cfg12-{tag}-v2-{i}", "v2", outcome, category))

    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"cfg12-exp-{tag}", "name": f"Stage12 E2E Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    return next(e["experiment_id"] for e in experiments if e["name"] == f"Stage12 E2E Test {tag}")


def test_self_service_onboarding_to_notified_rollback(api_client, test_identity, monkeypatch):
    captured_posts = []

    def fake_post(url, payload, timeout):
        captured_posts.append((url, payload))
        return 200

    import backend.notifications.client as notifications_client

    monkeypatch.setattr(notifications_client, "_default_post", fake_post)

    tag = f"cfg12-{uuid.uuid4().hex[:8]}"
    project_id = new_support_project(test_identity, "Stage12 Self-Service Project")

    # 1. Onboard entirely through the API: default primary metric, an
    # enabled notification rule, and a webhook channel -- no code/JSON edits.
    config_resp = api_client.put(
        f"/api/v1/domains/support/config?project_id={project_id}",
        json={"primary_metric": "resolution_rate", "enabled_notification_rules": ["ROLLBACK"]},
    )
    assert config_resp.status_code == 200

    channel_resp = api_client.post(
        f"/api/v1/notifications/channels?project_id={project_id}&domain=support",
        json={"channel_type": "webhook", "url": "https://example.com/hooks/team-alerts/supersecret"},
    )
    assert channel_resp.status_code == 201
    assert "supersecret" not in channel_resp.json()["url_preview"]

    # 2. Ingest a real regression.
    exp_id = _ingest_rollback_fixture(api_client, project_id, tag)

    status_before = api_client.get(f"/api/v1/domains/support/onboarding-status?project_id={project_id}").json()
    assert status_before["primary_metric_configured"] is True
    assert status_before["notifications_configured"] is True
    assert status_before["data_received"] is True

    # 3. Evaluate WITHOUT naming primary_metric -- the persisted default applies.
    eval_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?project_id={project_id}")
    assert eval_resp.status_code == 201
    body = eval_resp.json()
    assert body["primary_metric"] == "resolution_rate"
    assert body["status"] == "ROLLBACK"

    # 4. A real alert fired (existing Stage 6 machinery, unchanged)...
    alerts = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={project_id}").json()["alerts"]
    assert any(a["rule"] == "rollback" for a in alerts)

    # 5. ...and a notification was actually delivered to the configured channel.
    assert len(captured_posts) == 1
    posted_url, posted_payload = captured_posts[0]
    assert posted_url == "https://example.com/hooks/team-alerts/supersecret"
    assert posted_payload["event_type"] == "ROLLBACK"

    deliveries = api_client.get(f"/api/v1/notifications/deliveries?project_id={project_id}&domain=support").json()["deliveries"]
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "delivered"
    assert deliveries[0]["event_type"] == "ROLLBACK"
    assert "supersecret" not in deliveries[0]["payload_summary"]

    # 6. Re-evaluating the SAME experiment fires a NEW evaluation (new
    # dedup_key) -- proves this isn't accidentally deduped across distinct
    # real events, only within one.
    api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?project_id={project_id}")
    full = api_client.get(f"/api/v1/notifications/deliveries?project_id={project_id}&domain=support").json()
    assert len(full["deliveries"]) == 2
    assert full["total"] == 2 and full["limit"] == 50 and full["offset"] == 0

    # Stage 17 task 7: the delivery log grows one row per attempt
    # indefinitely -- pagination metadata (total/limit/offset) lets a
    # caller page through it instead of only ever seeing the newest 50.
    page1 = api_client.get(f"/api/v1/notifications/deliveries?project_id={project_id}&domain=support&limit=1&offset=0").json()
    page2 = api_client.get(f"/api/v1/notifications/deliveries?project_id={project_id}&domain=support&limit=1&offset=1").json()
    assert page1["total"] == 2 and page2["total"] == 2
    assert len(page1["deliveries"]) == 1 and len(page2["deliveries"]) == 1
    assert page1["deliveries"][0]["notification_id"] != page2["deliveries"][0]["notification_id"]
    assert page1["deliveries"][0]["notification_id"] == full["deliveries"][0]["notification_id"]
    assert page2["deliveries"][0]["notification_id"] == full["deliveries"][1]["notification_id"]
