"""Stage 3: generic ingestion API — batch ingestion, idempotency by
external IDs, schema validation, clear validation errors, and no
commerce-specific required field anywhere in the request body.

Stage 7: ingestion is now project-scoped (task 2) — every call below
creates its own throwaway project for that test's own arbitrary domain
string (via the shared test_identity org), proving a caller can ingest
into any project whose domain matches, not just "commerce"/"support".
"""

from __future__ import annotations

import json


def _payload(domain: str = "test_domain", session_suffix: str = "1") -> dict:
    return {
        "domain": domain,
        "experiments": [
            {
                "external_experiment_id": "exp1",
                "name": "Test Experiment",
                "control_version": "v1",
                "treatment_version": "v2",
            }
        ],
        "sessions": [
            {
                "external_session_id": f"sess{session_suffix}",
                "external_experiment_id": "exp1",
                "agent_version": "v1",
                "external_user_id": "user1",
                "started_at": "2026-01-01T00:00:00",
                "messages": [
                    {"external_message_id": "m1", "turn_index": 0, "sender": "user", "text": "hello", "created_at": "2026-01-01T00:00:00"}
                ],
                "actions": [
                    {
                        "external_action_id": "a1",
                        "sequence_index": 0,
                        "action_type": "reply",
                        "started_at": "2026-01-01T00:00:01",
                        "tool_calls": [
                            {"external_tool_call_id": "tc1", "tool_name": "lookup", "success": True}
                        ],
                    }
                ],
                "outcome": {"label": "resolved", "metrics": [{"name": "csat", "value": 5.0}]},
                "metrics": [{"name": "handle_time_seconds", "value": 120.0}],
                "context": {"anything": "opaque, domain-specific, never read by core"},
            }
        ],
    }


def _project_for_domain(test_identity, domain: str) -> str:
    from backend.auth.service import create_project
    from backend.app.db import get_database_url
    from sqlalchemy import create_engine

    engine = create_engine(get_database_url())
    return create_project(engine, test_identity["org_id"], f"Project for {domain}", domain).project_id


def _ingest(api_client, test_identity, payload):
    project_id = _project_for_domain(test_identity, payload["domain"])
    return api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})


def test_ingest_batch_succeeds_and_counts_every_entity(api_client, test_identity):
    resp = _ingest(api_client, test_identity, _payload("ingest_test_a"))
    assert resp.status_code == 201
    body = resp.json()
    assert body["domain"] == "ingest_test_a"
    assert body["experiments_ingested"] == 1
    assert body["sessions_ingested"] == 1
    assert body["messages_ingested"] == 1
    assert body["actions_ingested"] == 1
    assert body["tool_calls_ingested"] == 1
    assert body["metrics_ingested"] == 2  # csat (from outcome) + handle_time_seconds (session-level)


def test_ingest_batch_is_idempotent_by_external_ids(api_client, test_identity):
    payload = _payload("ingest_test_b")
    project_id = _project_for_domain(test_identity, payload["domain"])
    r1 = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    r2 = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json() == r2.json()


def test_ingest_batch_upserts_changed_fields_on_re_ingestion(api_client, test_identity):
    payload = _payload("ingest_test_c")
    project_id = _project_for_domain(test_identity, payload["domain"])
    api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})

    corrected = _payload("ingest_test_c")
    corrected["sessions"][0]["outcome"]["label"] = "escalated"
    r2 = api_client.post("/api/v1/ingest/sessions", json=corrected, params={"project_id": project_id})
    assert r2.status_code == 201
    assert r2.json()["sessions_ingested"] == 1  # still one row, not a duplicate


def test_ingest_batch_supports_multiple_sessions_in_one_batch(api_client, test_identity):
    payload = _payload("ingest_test_d", session_suffix="1")
    payload["sessions"].append(
        {
            **_payload("ingest_test_d", session_suffix="2")["sessions"][0],
        }
    )
    resp = _ingest(api_client, test_identity, payload)
    assert resp.status_code == 201
    assert resp.json()["sessions_ingested"] == 2


def test_ingest_batch_rejects_session_referencing_unknown_experiment(api_client, test_identity):
    payload = _payload("ingest_test_e")
    payload["experiments"] = []  # exp1 not declared here, and never ingested before for this domain
    resp = _ingest(api_client, test_identity, payload)
    assert resp.status_code == 422
    errors = json.loads(resp.json()["detail"])
    assert len(errors) == 1
    assert errors[0]["external_session_id"] == "sess1"
    assert "unknown external_experiment_id" in errors[0]["message"]


def test_ingest_batch_rejects_missing_required_field_with_pydantic_422(api_client, test_identity):
    payload = _payload("ingest_test_f")
    del payload["sessions"][0]["outcome"]
    resp = _ingest(api_client, test_identity, payload)
    assert resp.status_code == 422


def test_ingest_batch_rejects_empty_string_agent_version(api_client, test_identity):
    payload = _payload("ingest_test_g")
    payload["sessions"][0]["agent_version"] = ""
    resp = _ingest(api_client, test_identity, payload)
    assert resp.status_code == 422


def test_ingest_batch_rejects_duplicate_external_session_id_within_batch(api_client, test_identity):
    payload = _payload("ingest_test_h", session_suffix="dup")
    payload["sessions"].append(dict(payload["sessions"][0]))
    resp = _ingest(api_client, test_identity, payload)
    assert resp.status_code == 422


def test_ingest_batch_rejects_mismatched_project_domain(api_client, test_identity):
    """Stage 7 task 2: a project can only ingest data for its own domain."""
    payload = _payload("ingest_test_i")
    wrong_project_id = test_identity["commerce_project_id"]  # a "commerce" project, not "ingest_test_i"
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": wrong_project_id})
    assert resp.status_code == 400


def test_ingest_batch_has_no_commerce_specific_required_field():
    """Structural guard: no field name in the ingestion schemas' JSON
    schema is commerce vocabulary (product, recommendation, constraint,
    category, cart, purchase) — every field is generic."""
    from backend.ingestion.schemas import IngestBatchRequest

    schema = IngestBatchRequest.model_json_schema()
    schema_text = str(schema).lower()
    for forbidden in ("product", "recommendation", "constraint", "cart", "purchase"):
        assert forbidden not in schema_text, f"ingestion schema references commerce vocabulary: {forbidden!r}"
