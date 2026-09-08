"""Integration tests for /sessions* endpoints."""

from __future__ import annotations


def test_list_sessions_default(api_client):
    resp = api_client.get("/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 50 and body["offset"] == 0
    assert len(body["items"]) <= 50
    assert body["total"] > 0


def test_list_sessions_with_filters(api_client, experiment_id):
    resp = api_client.get("/sessions", params={"experiment_id": experiment_id, "agent_version": "v2", "requested_category": "monitor"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["filters_applied"] == {"agent_version": "v2", "requested_category": "monitor"}
    for item in body["items"]:
        assert item["agent_version"] == "v2"
        assert item["requested_category"] == "monitor"


def test_list_sessions_pagination(api_client):
    page1 = api_client.get("/sessions", params={"limit": 5, "offset": 0}).json()
    page2 = api_client.get("/sessions", params={"limit": 5, "offset": 5}).json()
    ids1 = {i["session_id"] for i in page1["items"]}
    ids2 = {i["session_id"] for i in page2["items"]}
    assert ids1.isdisjoint(ids2)
    assert page1["total"] == page2["total"]


def test_list_sessions_failure_mode_filter(api_client):
    resp = api_client.get("/sessions", params={"failure_mode": "unnecessary_clarification", "limit": 200})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 0
    assert all("unnecessary_clarification" in item["detected_failure_modes"] for item in body["items"])


def test_list_sessions_empty_result_for_impossible_filter_combo(api_client):
    """Sparse/empty result handling: a filter combination matching nothing
    must return 200 with an empty list, not an error."""
    resp = api_client.get("/sessions", params={"platform": "web", "device_tier": "low", "persona": "budget", "locale": "en-US", "requested_category": "accessory", "constraint_count_bucket": "3+", "outcome": "purchase", "agent_version": "v1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 0
    assert isinstance(body["items"], list)


def test_get_session_detail_reconstruction(api_client):
    session_id = api_client.get("/sessions", params={"limit": 1}).json()["items"][0]["session_id"]
    resp = api_client.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert len(body["transcript"]) >= 1
    assert len(body["agent_actions"]) >= 1
    assert body["agent_actions"][0]["action_type"] == "understand_query"
    # chronological order: sequence_index must be non-decreasing
    seqs = [a["sequence_index"] for a in body["agent_actions"]]
    assert seqs == sorted(seqs)


def test_session_transcript_is_chronologically_ordered(api_client):
    """Regression test for the sender-alphabetical-sort bug found in Stage 4
    review (ORDER BY turn_index, sender put every 'agent' message before
    the 'user' message in the same turn)."""
    resp = api_client.get("/sessions", params={"constraint_count_bucket": "3+", "limit": 100})
    multi_turn = [s for s in resp.json()["items"] if s["num_turns"] >= 2]
    assert len(multi_turn) > 0, "need at least one multi-turn session to test ordering"

    detail = api_client.get(f"/sessions/{multi_turn[0]['session_id']}").json()
    transcript = detail["transcript"]
    assert transcript[0]["sender"] == "user", "the very first message in any session must be the user's opener"


def test_session_agent_actions_expose_no_hidden_reasoning(api_client):
    session_id = api_client.get("/sessions", params={"limit": 1}).json()["items"][0]["session_id"]
    body = api_client.get(f"/sessions/{session_id}").json()
    # Stage 6: started_at / action_started_at were added so the frontend can
    # build one true merged timeline across messages/actions/tool_calls/
    # product_events (they don't share a comparable ordinal otherwise) —
    # these are observable timestamps, not hidden reasoning, so the
    # allow-list was extended to match rather than narrowed.
    allowed_keys = {"sequence_index", "action_type", "latency_ms", "model_name", "started_at"}
    for action in body["agent_actions"]:
        assert set(action.keys()) == allowed_keys
    for tool_call in body["tool_calls"]:
        assert set(tool_call.keys()) == {"tool_name", "success", "error_type", "latency_ms", "action_sequence_index", "action_started_at"}


def test_get_session_detail_includes_failure_attributions_with_provenance(api_client):
    resp = api_client.get("/sessions", params={"failure_mode": "unnecessary_clarification", "limit": 1})
    session_id = resp.json()["items"][0]["session_id"]
    detail = api_client.get(f"/sessions/{session_id}").json()
    attributions = detail["failure_attributions"]
    assert len(attributions) > 0
    fc = next(a for a in attributions if a["failure_mode"] == "unnecessary_clarification")
    assert fc["detector_source"] == "mock_llm"
    assert fc["provenance"]["is_mock"] is True
    assert fc["provenance"]["classifier_type"] == "rule_based_mock"
    assert fc["provenance"]["evaluation_status"] in ("evaluated_current", "evaluated_stale", "not_evaluated")


def test_get_unknown_session_404(api_client):
    resp = api_client.get("/sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_malformed_session_id_returns_404_not_500(api_client):
    resp = api_client.get("/sessions/not-a-uuid")
    assert resp.status_code == 404


def test_session_evaluations_are_only_deterministic_types(api_client):
    """answer_faithfulness (LLM-judged) has no rows yet (AI_EVALUATION.md
    SS6) — every evaluation exposed today must be rule_based."""
    session_id = api_client.get("/sessions", params={"outcome": "purchase", "limit": 1}).json()["items"][0]["session_id"]
    body = api_client.get(f"/sessions/{session_id}").json()
    for ev in body["evaluations"]:
        assert ev["evaluator"] == "rule_based"
        assert ev["eval_type"] in ("offline_task_success", "constraint_satisfaction")
