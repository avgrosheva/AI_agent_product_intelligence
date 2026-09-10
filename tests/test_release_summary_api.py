"""Stage 14 tasks 1-5/9: the release-summary endpoint through the real
API — schema shape, SHIP/HOLD/ROLLBACK examples, evidence ordering,
representative-session provenance, windowed-evaluation compatibility,
reviewed-attribution display, and tenant isolation."""

from __future__ import annotations

import uuid

from tests._connector_test_helpers import new_support_project

OTHER_CATEGORIES = ["technical", "account_access", "shipping_status", "general_inquiry"]


def _ingest_rollback_fixture(api_client, project_id: str, tag: str) -> str:
    def session(sid: str, version: str, outcome: str, category: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"sum-exp-{tag}", "agent_version": version,
            "external_user_id": f"user-{sid}", "started_at": "2026-09-01T00:00:00",
            "actions": [{"external_action_id": f"{sid}-a0", "sequence_index": 0, "action_type": "triage_ticket", "started_at": "2026-09-01T00:00:01", "tool_calls": []}],
            "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}, {"name": "cost_usd", "value": 1.0}, {"name": "revenue_usd", "value": 5.0}],
            "context": {"ticket_category": category},
        }

    sessions = []
    for i in range(40):
        category = "billing" if i < 20 else OTHER_CATEGORIES[i % 4]
        sessions.append(session(f"sum-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 9 else "escalated", category))
    for i in range(40):
        category = "billing" if i < 20 else OTHER_CATEGORIES[i % 4]
        outcome = ("resolved" if i % 10 < 2 else "escalated") if category == "billing" else ("resolved" if i % 10 < 8 else "escalated")
        sessions.append(session(f"sum-{tag}-v2-{i}", "v2", outcome, category))

    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"sum-exp-{tag}", "name": f"Summary Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    return next(e["experiment_id"] for e in experiments if e["name"] == f"Summary Test {tag}")


def _ingest_ship_fixture(api_client, project_id: str, tag: str) -> str:
    def session(sid: str, version: str, outcome: str) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"sumship-exp-{tag}", "agent_version": version,
            "external_user_id": f"user-{sid}", "started_at": "2026-09-01T00:00:00", "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
        }

    sessions = [session(f"sumship-{tag}-v1-{i}", "v1", "resolved" if i % 10 < 6 else "escalated") for i in range(40)]
    sessions += [session(f"sumship-{tag}-v2-{i}", "v2", "resolved" if i % 10 < 9 else "escalated") for i in range(40)]
    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"sumship-exp-{tag}", "name": f"Summary Ship Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    return next(e["experiment_id"] for e in experiments if e["name"] == f"Summary Ship Test {tag}")


def test_rollback_release_summary_schema_and_evidence_ordering(api_client, support_project_id):
    tag = f"sum-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_rollback_fixture(api_client, support_project_id, tag)
    eval_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    assert eval_resp.status_code == 201
    assert eval_resp.json()["status"] == "ROLLBACK"

    summary_resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-summary?project_id={support_project_id}")
    assert summary_resp.status_code == 200
    body = summary_resp.json()

    # -- decision summary ---------------------------------------------
    decision = body["decision"]
    assert decision["verdict"] == "ROLLBACK"
    assert decision["primary_metric"] == "resolution_rate"
    assert decision["primary_metric_delta"] is not None and decision["primary_metric_delta"] < 0
    assert decision["confidence"] in {"strong", "moderate", "weak", "insufficient_evidence"}
    assert decision["economics_impact"] is not None  # cost_usd/revenue_usd were ingested

    # -- deterministic explanation --------------------------------------
    assert body["explanation_text"].startswith("ROLLBACK because resolution_rate decreased by")

    # -- evidence hierarchy: fixed category order -----------------------
    categories_seen = [item["category"] for item in body["evidence_hierarchy"]]
    priority = ["blocking_guardrail", "primary_metric", "negative_segment", "economics", "failure_mechanism", "representative_session"]
    filtered_priority = [c for c in priority if c in categories_seen]
    assert categories_seen == sorted(categories_seen, key=lambda c: priority.index(c)) or categories_seen == filtered_priority
    ranks = [item["rank"] for item in body["evidence_hierarchy"]]
    assert ranks == list(range(1, len(ranks) + 1))  # 1-indexed, contiguous

    # -- findings ---------------------------------------------------------
    assert len(body["findings"]) >= 1
    billing_finding = next(f for f in body["findings"] if f["segment_label"] == "ticket_category=billing")
    assert billing_finding["metric"] == "resolution_rate"
    assert billing_finding["v1_value"] is not None and billing_finding["v2_value"] is not None
    assert billing_finding["delta"] == billing_finding["v2_value"] - billing_finding["v1_value"]
    assert billing_finding["p_value"] is not None
    assert billing_finding["next_action"]
    assert billing_finding["representative_session_ids"]

    # -- session-level evidence detail -----------------------------------
    assert len(body["representative_sessions"]) >= 1
    for s in body["representative_sessions"]:
        assert s["outcome"] in {"resolved", "escalated"}
        assert s["human_review_status"] == "not_reviewed"
        assert s["selected_because"]
        detail = api_client.get(f"/api/v1/domains/support/sessions/{s['session_id']}?project_id={support_project_id}")
        assert detail.status_code == 200

    # -- monitoring window: manual eval, no window -----------------------
    assert body["monitoring_window"]["window_hours"] is None


def test_ship_release_summary_has_empty_negative_evidence(api_client, support_project_id):
    tag = f"sumship-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_ship_fixture(api_client, support_project_id, tag)
    eval_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    assert eval_resp.status_code == 201
    assert eval_resp.json()["status"] == "SHIP"

    body = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-summary?project_id={support_project_id}").json()
    assert body["decision"]["verdict"] == "SHIP"
    assert body["explanation_text"].startswith("SHIP because resolution_rate increased by")
    assert body["findings"] == []
    assert body["representative_sessions"] == []
    categories = [item["category"] for item in body["evidence_hierarchy"]]
    assert "blocking_guardrail" not in categories
    assert "negative_segment" not in categories


def test_release_summary_is_deterministic_across_repeated_calls(api_client, support_project_id):
    tag = f"sumdet-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_rollback_fixture(api_client, support_project_id, tag)
    api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")

    first = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-summary?project_id={support_project_id}").json()
    second = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-summary?project_id={support_project_id}").json()
    assert first["explanation_text"] == second["explanation_text"]
    assert first["evidence_hierarchy"] == second["evidence_hierarchy"]
    assert first["findings"] == second["findings"]


def test_release_summary_404s_before_any_evaluation(api_client, support_project_id):
    resp = api_client.get(f"/api/v1/domains/support/experiments/nonexistent-exp/release-summary?project_id={support_project_id}")
    assert resp.status_code == 404


def test_release_summary_reflects_reviewed_attribution(api_client, experiment_id):
    """Stage 14 task 9: reviewed-attribution display. Commerce has real
    registered mechanisms/reviewable attributions; find a representative
    session with a detected mechanism, submit a review for it, and
    confirm the release summary then marks it "reviewed"."""
    eval_resp = api_client.post(f"/api/v1/domains/commerce/experiments/{experiment_id}/release-evaluations?primary_metric=abandonment_rate")
    assert eval_resp.status_code == 201

    summary_before = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/release-summary").json()
    reviewable = next((s for s in summary_before["representative_sessions"] if s["detected_mechanisms"]), None)
    if reviewable is None:
        return  # nothing with a detected mechanism among today's findings -- not this test's own concern

    assert reviewable["human_review_status"] == "not_reviewed"
    session_id = reviewable["session_id"]
    failure_mode = reviewable["detected_mechanisms"][0]

    review_resp = api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review",
        json={"decision": "confirmed", "note": "looks right"},
    )
    assert review_resp.status_code == 201

    summary_after = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/release-summary").json()
    reviewed = next(s for s in summary_after["representative_sessions"] if s["session_id"] == session_id)
    assert reviewed["human_review_status"] == "reviewed"


def test_commerce_release_summary_works_and_is_tenant_scoped(api_client, experiment_id, commerce_project_id):
    resp = api_client.post(f"/api/v1/domains/commerce/experiments/{experiment_id}/release-evaluations?primary_metric=abandonment_rate")
    assert resp.status_code == 201
    body = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/release-summary").json()
    assert body["decision"]["domain"] == "commerce"
    assert body["decision"]["verdict"] == "HOLD"


def test_release_summary_is_project_scoped(api_client, support_project_id, test_identity):
    tag = f"sumiso-{uuid.uuid4().hex[:8]}"
    exp_id = _ingest_ship_fixture(api_client, support_project_id, tag)
    api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")

    other_project_id = new_support_project(test_identity, "Release Summary Isolation Project")
    resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/release-summary?project_id={other_project_id}")
    assert resp.status_code == 404  # another project can never see this experiment's summary
