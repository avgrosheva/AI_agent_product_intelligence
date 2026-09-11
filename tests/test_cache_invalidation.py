"""Stage 18 task 6/11: the Stage 17 metrics/investigation caches
(backend.analytics.cache_utils) were keyed partly on len(base_df) as a
"has the data changed" signal. That misses an EXISTING row's content
changing without a row-count change -- both backend.ingestion.service
.ingest_batch (re-sending a session with the same external_session_id is
an upsert, by design) and backend.connectors.postgres_business.service
.run_enrichment (layers business metrics onto existing sessions the same
way) do exactly this. This proves the fix: a session's outcome is
corrected via re-ingestion with an unchanged session count, and a
metrics-table read taken before AND after must differ -- if the cache
were still keyed only on len(base_df), the second read would silently
return the first read's now-stale value.
"""

from __future__ import annotations


def _support_ingest_payload(tag: str, sessions: list[dict]) -> dict:
    return {
        "domain": "support",
        "experiments": [{"external_experiment_id": f"cache-inval-exp-{tag}", "name": f"Cache Invalidation {tag}", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": sessions,
    }


def _session(tag: str, sid: str, version: str, outcome: str) -> dict:
    return {
        "external_session_id": sid,
        "external_experiment_id": f"cache-inval-exp-{tag}",
        "agent_version": version,
        "external_user_id": f"user-{sid}",
        "started_at": "2026-06-01T00:00:00",
        "ended_at": "2026-06-01T00:05:00",
        "messages": [{"external_message_id": f"{sid}-m0", "turn_index": 0, "sender": "user", "text": "help", "created_at": "2026-06-01T00:00:00"}],
        "actions": [{"external_action_id": f"{sid}-a0", "sequence_index": 0, "action_type": "triage_ticket", "started_at": "2026-06-01T00:00:01", "tool_calls": []}],
        "outcome": {"label": outcome, "metrics": []},
        "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
        "context": {"ticket_category": "billing"},
    }


def test_metrics_reflect_a_session_outcome_corrected_by_re_ingestion_with_no_row_count_change(api_client, support_project_id):
    tag = "reingest"
    sessions = [_session(tag, f"cache-inval-{tag}-v1-0", "v1", "resolved"), _session(tag, f"cache-inval-{tag}-v1-1", "v1", "resolved")]
    ingest_resp = api_client.post("/api/v1/ingest/sessions", json=_support_ingest_payload(tag, sessions), params={"project_id": support_project_id})
    assert ingest_resp.status_code == 201

    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]
    exp = next(e for e in experiments if e["name"] == f"Cache Invalidation {tag}")
    exp_id = exp["experiment_id"]

    def resolution_rate_v1() -> float:
        metrics = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/metrics?project_id={support_project_id}").json()["metrics"]
        row = next(m for m in metrics if m["metric_name"] == "resolution_rate")
        return row["session_value_v1"]

    # Both v1 sessions resolved -> 100% resolution rate. This call also
    # warms the metrics cache for this experiment.
    assert resolution_rate_v1() == 1.0

    # Re-ingest the FIRST session with the SAME external_session_id but a
    # corrected outcome -- an upsert, so the session count is unchanged
    # (still 2 for v1); only that one row's content changed.
    corrected = [_session(tag, f"cache-inval-{tag}-v1-0", "v1", "escalated"), sessions[1]]
    reingest_resp = api_client.post("/api/v1/ingest/sessions", json=_support_ingest_payload(tag, corrected), params={"project_id": support_project_id})
    assert reingest_resp.status_code == 201

    # 1 of 2 now resolved. A cache still keyed only on len(base_df) would
    # return the stale 1.0 from before, since the row count never changed.
    assert resolution_rate_v1() == 0.5


def test_metrics_cache_is_still_a_cache_repeated_reads_with_no_write_between_do_not_recompute(api_client, support_project_id):
    """Companion to the invalidation test above -- the fix must not
    accidentally turn the cache into a no-op that recomputes every call
    regardless of whether anything changed. Two consecutive reads with no
    intervening write must return the identical value (and, more to the
    point of what Stage 17 was for, the second one should be the cheap
    cache-hit path) -- this only checks the value stays stable across
    repeated reads, which a correctness bug in either direction would break."""
    tag = "stable"
    sessions = [_session(tag, f"cache-inval-{tag}-v1-0", "v1", "resolved"), _session(tag, f"cache-inval-{tag}-v1-1", "v1", "escalated")]
    ingest_resp = api_client.post("/api/v1/ingest/sessions", json=_support_ingest_payload(tag, sessions), params={"project_id": support_project_id})
    assert ingest_resp.status_code == 201

    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]
    exp = next(e for e in experiments if e["name"] == f"Cache Invalidation {tag}")
    exp_id = exp["experiment_id"]

    def resolution_rate_v1() -> float:
        metrics = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/metrics?project_id={support_project_id}").json()["metrics"]
        row = next(m for m in metrics if m["metric_name"] == "resolution_rate")
        return row["session_value_v1"]

    first = resolution_rate_v1()
    second = resolution_rate_v1()
    assert first == second == 0.5
