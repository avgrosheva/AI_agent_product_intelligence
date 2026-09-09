"""Stage 11 tasks 3-4/9: the release-evidence endpoint proven through the
real API — evidence references real, re-fetchable sessions (not
fabricated ids), breached guardrails/negative segments come straight from
the persisted evaluation, and a SHIP evaluation (nothing negative to
report) returns empty evidence rather than erroring."""

from __future__ import annotations

import uuid


OTHER_CATEGORIES = ["technical", "account_access", "shipping_status", "general_inquiry"]


def _ingest_rollback_fixture(api_client, project_id: str, tag: str) -> str:
    """Unlike tests/test_alerts_integration.py's own rollback fixture
    (a single fixed ticket_category, sufficient to prove ROLLBACK but
    never sufficient for a per-segment finding — support's only segment
    dimension IS ticket_category), this fixture also varies category:
    "billing" regresses much harder in v2 than the other four categories,
    so the segment scan flags "billing" as a significant negative segment
    on top of the overall ROLLBACK verdict — needed to exercise the
    evidence layer's negative-segment/representative-session output."""

    def session(sid: str, version: str, outcome: str, category: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"evid-exp-{tag}", "agent_version": version, "external_user_id": f"user-{sid}",
            "started_at": "2026-09-01T00:00:00",
            "actions": [{"external_action_id": f"{sid}-a0", "sequence_index": 0, "action_type": "triage_ticket", "started_at": "2026-09-01T00:00:01", "tool_calls": []}],
            "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
            "context": {"ticket_category": category},
        }

    sessions = []
    for i in range(40):
        category = "billing" if i < 20 else OTHER_CATEGORIES[i % 4]
        sessions.append(session(f"evid-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 9 else "escalated", category))
    for i in range(40):
        category = "billing" if i < 20 else OTHER_CATEGORIES[i % 4]
        if category == "billing":
            outcome = "resolved" if i % 10 < 2 else "escalated"  # 90% -> 20%: sharp, segment-level regression
        else:
            outcome = "resolved" if i % 10 < 8 else "escalated"  # 90% -> 80%: mild, not independently significant
        sessions.append(session(f"evid-{tag}-v2-{i}", "v2", outcome, category))

    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"evid-exp-{tag}", "name": f"Evidence Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    return next(e["experiment_id"] for e in experiments if e["name"] == f"Evidence Test {tag}")


def _ingest_ship_fixture(api_client, project_id: str, tag: str) -> str:
    def session(sid: str, version: str, outcome: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"evid-ship-exp-{tag}", "agent_version": version, "external_user_id": f"user-{sid}",
            "started_at": "2026-09-01T00:00:00", "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
        }

    sessions = [session(f"evidship-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 6 else "escalated") for i in range(40)]
    sessions += [session(f"evidship-{tag}-v2-{i}", "v2", "resolved" if i % 10 < 9 else "escalated") for i in range(40)]
    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"evid-ship-exp-{tag}", "name": f"Evidence Ship Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    return next(e["experiment_id"] for e in experiments if e["name"] == f"Evidence Ship Test {tag}")


def test_evidence_references_real_re_fetchable_sessions(api_client, support_project_id):
    tag = f"evid-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_rollback_fixture(api_client, support_project_id, tag)
    eval_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    assert eval_resp.status_code == 201
    evaluation_id = eval_resp.json()["evaluation_id"]
    assert eval_resp.json()["status"] == "ROLLBACK"

    evidence_resp = api_client.get(
        f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations/{evaluation_id}/evidence?project_id={support_project_id}"
    )
    assert evidence_resp.status_code == 200
    body = evidence_resp.json()
    assert body["status"] == "ROLLBACK"
    assert len(body["significant_negative_segments"]) >= 1

    all_session_ids = {sid for seg in body["significant_negative_segments"] for sid in seg["representative_session_ids"]}
    assert all_session_ids  # at least one representative session was selected
    assert {s["session_id"] for s in body["representative_sessions"]} <= all_session_ids

    # Every representative session is real and independently re-fetchable
    # through the ordinary session-detail endpoint -- evidence never
    # points at a session that doesn't actually exist.
    for session_evidence in body["representative_sessions"]:
        detail = api_client.get(f"/api/v1/domains/support/sessions/{session_evidence['session_id']}?project_id={support_project_id}")
        assert detail.status_code == 200
        assert detail.json()["session_id"] == session_evidence["session_id"]
        assert session_evidence["outcome"] in {"resolved", "escalated", "abandoned"}


def test_evidence_representative_session_selection_is_deterministic(api_client, support_project_id):
    tag = f"evidrepeat-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_rollback_fixture(api_client, support_project_id, tag)
    first = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}").json()
    second = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}").json()

    ev1 = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations/{first['evaluation_id']}/evidence?project_id={support_project_id}").json()
    ev2 = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations/{second['evaluation_id']}/evidence?project_id={support_project_id}").json()

    ids1 = sorted(sid for seg in ev1["significant_negative_segments"] for sid in seg["representative_session_ids"])
    ids2 = sorted(sid for seg in ev2["significant_negative_segments"] for sid in seg["representative_session_ids"])
    assert ids1 == ids2  # same underlying data -> same representative sessions, every time


def test_ship_evaluation_has_empty_negative_evidence(api_client, support_project_id):
    tag = f"evidship-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_ship_fixture(api_client, support_project_id, tag)
    eval_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    assert eval_resp.status_code == 201
    assert eval_resp.json()["status"] == "SHIP"
    evaluation_id = eval_resp.json()["evaluation_id"]

    evidence_resp = api_client.get(
        f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations/{evaluation_id}/evidence?project_id={support_project_id}"
    )
    assert evidence_resp.status_code == 200
    body = evidence_resp.json()
    assert body["significant_negative_segments"] == []
    assert body["representative_sessions"] == []
    assert body["breached_guardrails"] == []


def test_evidence_404s_for_unknown_evaluation_id(api_client, support_project_id):
    resp = api_client.get(
        f"/api/v1/domains/support/experiments/nonexistent/release-evaluations/00000000-0000-0000-0000-000000000000/evidence?project_id={support_project_id}"
    )
    assert resp.status_code == 404
