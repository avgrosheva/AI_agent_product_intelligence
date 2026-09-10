"""Stage 13: the core proof that window_hours actually constrains
release analysis. One fixture where the FULL history looks like a clean
SHIP (a large historical improvement dwarfs a small, very recent
regression) but a SHORT windowed evaluation — seeing only the recent
regression — reaches ROLLBACK: different metrics, a guardrail that only
breaches when windowed, provenance persisted on both the ReleaseEvaluation
and the MonitoringRun, and the resulting alert/notification referencing
that exact windowed evaluation. A second, separate fixture proves segment
findings and evidence never escape the window. A manual (unwindowed)
evaluation is proven byte-compatible with pre-Stage-13 behavior."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests._connector_test_helpers import new_support_project

WINDOW_HOURS = 6


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat()


def _build_window_fixture(tag: str):
    """OLD period (10 days ago, well outside a 6h window): 200 v1 @ 80%
    resolved, 200 v2 @ 98% resolved (v2 clearly better — a genuine past
    improvement). RECENT period (1 hour ago, inside a 6h window): 20 v1 @
    80% resolved (consistent baseline), 20 v2 @ 20% resolved (a sharp,
    brand-new regression). Full history blends these (v2 still net better
    overall -> SHIP); the windowed evaluation sees ONLY the recent
    regression -> ROLLBACK. Escalation guardrail: full-history escalation
    rate goes DOWN (safe); windowed escalation rate goes sharply UP
    (breached) — guardrails are windowed. A "cost_usd" metric (1.0 old,
    9.0 recent) makes the economics figures differ by window too."""
    now = datetime.now(timezone.utc)
    old_ts = _iso(now - timedelta(days=10))
    recent_ts = _iso(now - timedelta(hours=1))

    def session(sid: str, version: str, outcome: str, started_at: str, cost: float) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"win13-exp-{tag}", "agent_version": version,
            "external_user_id": f"user-{sid}", "started_at": started_at, "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}, {"name": "cost_usd", "value": cost}],
            "context": {"ticket_category": "general_inquiry"},
        }

    sessions = []
    for i in range(200):
        sessions.append(session(f"win13-{tag}-old-v1-{i}", "v1", "resolved" if i % 10 < 8 else "escalated", old_ts, 1.0))
    for i in range(200):
        sessions.append(session(f"win13-{tag}-old-v2-{i}", "v2", "resolved" if i % 100 < 98 else "escalated", old_ts, 1.0))
    for i in range(20):
        sessions.append(session(f"win13-{tag}-recent-v1-{i}", "v1", "resolved" if i % 10 < 8 else "escalated", recent_ts, 9.0))
    for i in range(20):
        sessions.append(session(f"win13-{tag}-recent-v2-{i}", "v2", "resolved" if i % 10 < 2 else "escalated", recent_ts, 9.0))

    payload = {
        "domain": "support",
        "experiments": [{"external_experiment_id": f"win13-exp-{tag}", "name": f"Stage13 Window Test {tag}", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": sessions,
    }
    return payload


def _ingest(api_client, project_id: str, tag: str) -> str:
    payload = _build_window_fixture(tag)
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201
    assert resp.json()["sessions_ingested"] == 440
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    return next(e["experiment_id"] for e in experiments if e["name"] == f"Stage13 Window Test {tag}")


def test_full_history_ships_but_short_window_rolls_back(api_client, test_identity, monkeypatch):
    captured_posts = []

    def fake_post(url, payload, timeout):
        captured_posts.append(payload)
        return 200

    import backend.notifications.client as notifications_client

    monkeypatch.setattr(notifications_client, "_default_post", fake_post)

    tag = f"w13-{uuid.uuid4().hex[:8]}"
    project_id = new_support_project(test_identity, "Stage13 Window Project")
    exp_id = _ingest(api_client, project_id, tag)

    api_client.put(f"/api/v1/domains/support/config?project_id={project_id}", json={"enabled_notification_rules": ["ROLLBACK"]})
    channel_resp = api_client.post(
        f"/api/v1/notifications/channels?project_id={project_id}&domain=support",
        json={"channel_type": "webhook", "url": "https://example.com/hooks/win13"},
    )
    assert channel_resp.status_code == 201

    # Manual, unwindowed evaluation -- the full 440-session history.
    full_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={project_id}")
    assert full_resp.status_code == 201
    full = full_resp.json()
    assert full["status"] == "SHIP"
    assert full["any_guardrail_breach"] is False
    assert full["data_window_start"] is None  # task 4: manual evaluation stores no window at all
    assert full["data_window_end"] is None
    assert full["window_hours"] is None
    full_v2_resolution = full["key_metrics"]["resolution_rate"]["v2"]

    # A monitoring config with a short recent window, run on demand.
    config_resp = api_client.post(
        f"/api/v1/monitoring/configs?project_id={project_id}",
        json={"domain": "support", "experiment_id": exp_id, "primary_metric": "resolution_rate", "cadence_seconds": 3600, "window_hours": WINDOW_HOURS},
    )
    assert config_resp.status_code == 201
    config_id = config_resp.json()["config_id"]

    trigger = api_client.post(f"/api/v1/monitoring/configs/{config_id}/run-now?project_id={project_id}&domain=support")
    assert trigger.status_code == 202

    run = api_client.get(f"/api/v1/monitoring/configs/{config_id}/latest?project_id={project_id}&domain=support").json()
    assert run["status"] == "succeeded"
    assert run["window_hours"] == WINDOW_HOURS
    assert run["data_window_start"] is not None
    assert run["data_window_end"] is not None
    windowed_evaluation_id = run["release_evaluation_id"]

    windowed = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-status?project_id={project_id}").json()
    assert windowed["evaluation_id"] == windowed_evaluation_id

    # -- task 8: the window materially changes the decision --------------
    assert windowed["status"] == "ROLLBACK"
    assert full["status"] != windowed["status"]

    # -- provenance persisted on the ReleaseEvaluation itself -------------
    assert windowed["window_hours"] == WINDOW_HOURS
    assert windowed["data_window_start"] is not None
    assert windowed["data_window_end"] is not None

    # -- different window sizes/scopes -> different metrics ---------------
    windowed_v2_resolution = windowed["key_metrics"]["resolution_rate"]["v2"]
    assert windowed_v2_resolution != full_v2_resolution
    assert windowed_v2_resolution < 0.5 < full_v2_resolution  # ~20% windowed vs ~91% full history

    # -- guardrails are windowed: no breach full-history, breached windowed
    assert windowed["any_guardrail_breach"] is True
    assert any(g["name"] == "escalation_rate_guardrail" for g in windowed["breached_guardrails"])

    # -- economics are windowed: cost_usd was 1.0 (old) vs 9.0 (recent) ---
    full_cost_v1 = full["economics"]["cost_per_session_v1"]
    windowed_cost_v1 = windowed["economics"]["cost_per_session_v1"]
    assert windowed_cost_v1 == pytest.approx(9.0)
    assert full_cost_v1 < 2.0  # dominated by the 200 old sessions @ 1.0

    # -- alerts/notifications reference the WINDOWED evaluation ----------
    alerts = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={project_id}").json()["alerts"]
    rollback_alerts = [a for a in alerts if a["rule"] == "rollback"]
    assert len(rollback_alerts) == 1
    assert rollback_alerts[0]["evaluation_id"] == windowed_evaluation_id

    # Exactly one ROLLBACK notification fired -- for the WINDOWED
    # evaluation (the full-history one was SHIP, no notification), and
    # its payload is the windowed numbers, never recomputed against
    # full-history data.
    assert len(captured_posts) == 1
    assert captured_posts[0]["dedup_key"] == windowed_evaluation_id
    assert captured_posts[0]["event_type"] == "ROLLBACK"
    assert captured_posts[0]["status"] == "ROLLBACK"

    deliveries = api_client.get(f"/api/v1/notifications/deliveries?project_id={project_id}&domain=support").json()["deliveries"]
    assert len(deliveries) == 1
    assert deliveries[0]["dedup_key"] == windowed_evaluation_id
    assert deliveries[0]["status"] == "delivered"


def test_segment_findings_and_evidence_never_escape_the_window(api_client, test_identity):
    """Stage 13 tasks 6/9: old (out-of-window) sessions all share a flat,
    unaffected category; only inside the window does a "billing" segment
    show a sharp regression. Every representative session the windowed
    evaluation's evidence points to must have started_at inside the
    window — never one of the old, out-of-window sessions."""
    from sqlalchemy import create_engine, text

    from backend.app.db import get_database_url

    tag = f"w13seg-{uuid.uuid4().hex[:8]}"
    project_id = new_support_project(test_identity, "Stage13 Segment Window Project")
    now = datetime.now(timezone.utc)
    old_ts = _iso(now - timedelta(days=10))
    recent_ts = _iso(now - timedelta(hours=1))

    def session(sid: str, version: str, outcome: str, started_at: str, category: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"win13seg-exp-{tag}", "agent_version": version,
            "external_user_id": f"user-{sid}", "started_at": started_at, "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}], "context": {"ticket_category": category},
        }

    sessions = []
    for i in range(40):
        sessions.append(session(f"w13seg-{tag}-old-v1-{i}", "v1", "resolved" if i % 10 < 9 else "escalated", old_ts, "general_inquiry"))
    for i in range(40):
        sessions.append(session(f"w13seg-{tag}-old-v2-{i}", "v2", "resolved" if i % 10 < 9 else "escalated", old_ts, "general_inquiry"))
    for i in range(30):
        sessions.append(session(f"w13seg-{tag}-recent-billing-v1-{i}", "v1", "resolved" if i % 10 < 9 else "escalated", recent_ts, "billing"))
    for i in range(30):
        sessions.append(session(f"w13seg-{tag}-recent-billing-v2-{i}", "v2", "resolved" if i % 20 < 1 else "escalated", recent_ts, "billing"))
    for i in range(30):
        sessions.append(session(f"w13seg-{tag}-recent-tech-v1-{i}", "v1", "resolved" if i % 10 < 9 else "escalated", recent_ts, "technical"))
    for i in range(30):
        sessions.append(session(f"w13seg-{tag}-recent-tech-v2-{i}", "v2", "resolved" if i % 10 < 9 else "escalated", recent_ts, "technical"))

    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"win13seg-exp-{tag}", "name": f"Stage13 Segment Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    ingest_resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert ingest_resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    exp_id = next(e["experiment_id"] for e in experiments if e["name"] == f"Stage13 Segment Test {tag}")

    config_resp = api_client.post(
        f"/api/v1/monitoring/configs?project_id={project_id}",
        json={"domain": "support", "experiment_id": exp_id, "primary_metric": "resolution_rate", "cadence_seconds": 3600, "window_hours": WINDOW_HOURS},
    )
    config_id = config_resp.json()["config_id"]
    api_client.post(f"/api/v1/monitoring/configs/{config_id}/run-now?project_id={project_id}&domain=support")
    run = api_client.get(f"/api/v1/monitoring/configs/{config_id}/latest?project_id={project_id}&domain=support").json()
    assert run["status"] == "succeeded"
    evaluation_id = run["release_evaluation_id"]
    window_start = datetime.fromisoformat(run["data_window_start"])
    window_end = datetime.fromisoformat(run["data_window_end"])

    evidence = api_client.get(
        f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations/{evaluation_id}/evidence?project_id={project_id}"
    ).json()
    assert len(evidence["significant_negative_segments"]) >= 1
    assert any(s["segment_label"] == "ticket_category=billing" for s in evidence["significant_negative_segments"])

    all_representative_ids = {sid for seg in evidence["significant_negative_segments"] for sid in seg["representative_session_ids"]}
    assert all_representative_ids  # at least one representative session was selected

    engine = create_engine(get_database_url())
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT session_id, started_at FROM ingested_sessions WHERE session_id = ANY(:ids)"),
            {"ids": list(all_representative_ids)},
        ).all()
    assert len(rows) == len(all_representative_ids)
    for _, started_at in rows:
        assert window_start <= started_at <= window_end  # never one of the old, out-of-window sessions

    # And every session actually returned in `representative_sessions` is
    # independently re-fetchable and real (Stage 11's own guarantee, still
    # true here).
    for session_evidence in evidence["representative_sessions"]:
        detail = api_client.get(f"/api/v1/domains/support/sessions/{session_evidence['session_id']}?project_id={project_id}")
        assert detail.status_code == 200


def test_commerce_manual_evaluation_unaffected_by_window_provenance_fields(api_client, experiment_id):
    """Stage 13 task 4/9: commerce/support compatibility -- adding window
    provenance columns/params must not change a manual commerce
    evaluation's own behavior or response shape."""
    resp = api_client.post(f"/api/v1/domains/commerce/experiments/{experiment_id}/release-evaluations?primary_metric=abandonment_rate")
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "HOLD"
    assert body["data_window_start"] is None
    assert body["data_window_end"] is None
    assert body["window_hours"] is None
