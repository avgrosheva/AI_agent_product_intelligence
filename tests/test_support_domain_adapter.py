"""Stage 3 task 6 proof, as a fast pytest: a small non-commerce
(support-agent) fixture, ingested through the generic API, can be
compared v1-vs-v2 with the generic metric/guardrail mechanisms, and the
domain has zero registered failure mechanisms — without touching
backend.app.models or any commerce table."""

from __future__ import annotations

from backend.analytics.experiment_results import analyze_metric
from backend.core.guardrails import evaluate_guardrails
from backend.domains.support.adapter import SupportAdapter


def _support_payload(domain: str) -> dict:
    def session(sid: str, version: str, outcome: str, handle_time: float, csat: float | None) -> dict:
        metrics = [{"name": "handle_time_seconds", "value": handle_time}]
        outcome_metrics = [{"name": "csat_score", "value": csat}] if csat is not None else []
        return {
            "external_session_id": sid,
            "external_experiment_id": "support-exp",
            "agent_version": version,
            "external_user_id": f"user-{sid}",
            "started_at": "2026-01-01T00:00:00",
            "ended_at": "2026-01-01T00:05:00",
            "messages": [{"external_message_id": f"{sid}-m0", "turn_index": 0, "sender": "user", "text": "help", "created_at": "2026-01-01T00:00:00"}],
            "actions": [{"external_action_id": f"{sid}-a0", "sequence_index": 0, "action_type": "triage_ticket", "started_at": "2026-01-01T00:00:01", "tool_calls": []}],
            "outcome": {"label": outcome, "metrics": outcome_metrics},
            "metrics": metrics,
            "context": {"ticket_category": "billing"},
        }

    sessions = []
    for i in range(12):
        sessions.append(session(f"v1-{i}", "v1", "resolved" if i % 3 != 0 else "escalated", 400.0, 3.8 if i % 3 != 0 else None))
    for i in range(12):
        sessions.append(session(f"v2-{i}", "v2", "resolved" if i % 6 != 0 else "escalated", 250.0, 4.4 if i % 6 != 0 else None))

    return {
        "domain": domain,
        "experiments": [{"external_experiment_id": "support-exp", "name": "Support Test", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": sessions,
    }


def test_support_domain_has_no_registered_mechanisms(db_engine):
    from sqlalchemy import create_engine

    from backend.app.db import get_database_url

    adapter = SupportAdapter(create_engine(get_database_url()))
    assert adapter.mechanisms().all_names == ()


def test_support_domain_end_to_end_ingest_compare_guardrail(api_client, db_engine):
    # SupportAdapter.domain is the fixed string "support" (analytics_base_df
    # filters ingested_sessions by it) — the payload must be ingested under
    # that same domain. This is safe against cross-test collisions because
    # tests run against the isolated per-session test database (Stage 1's
    # test/demo DB isolation fix), never the demo database a real "support"
    # fixture might also use.
    domain = SupportAdapter.domain
    resp = api_client.post("/api/v1/ingest/sessions", json=_support_payload(domain))
    assert resp.status_code == 201
    assert resp.json()["sessions_ingested"] == 24

    from sqlalchemy import create_engine

    from backend.app.db import get_database_url

    adapter = SupportAdapter(create_engine(get_database_url()))
    base_df = adapter.analytics_base_df()
    # No further scoping needed: this test runs against the isolated
    # per-session test database (Stage 1's test/demo DB isolation fix),
    # and this is the only test in the suite that ingests domain="support"
    # data, so every row in ingested_sessions for this domain is this
    # test's own.
    assert len(base_df) == 24

    resolution_metric = next(m for m in adapter.metric_definitions() if m.name == "resolution_rate")
    result = analyze_metric(base_df, resolution_metric, metric_value_columns=adapter.metric_value_columns())
    assert result.session_value_v1 < result.session_value_v2  # v2 resolves more often, by construction

    csat_metric = next(m for m in adapter.metric_definitions() if m.name == "csat_score")
    csat_result = analyze_metric(base_df, csat_metric, metric_value_columns=adapter.metric_value_columns())
    assert csat_result.session_value_v1 < csat_result.session_value_v2

    report = evaluate_guardrails(base_df, adapter.guardrails())
    assert len(report.checks) == 1
    assert report.checks[0].name == "escalation_rate_guardrail"

    sample_session_id = base_df.iloc[0]["session_id"]
    ctx = adapter.build_session_context(sample_session_id)
    assert ctx.outcome in ("resolved", "escalated")
    assert ctx.action_sequence == ("triage_ticket",)
