"""Stage 4 task 5 proof: the full generic Investigation pipeline
(segment scan over the support domain's own pre-treatment dimension,
Benjamini-Hochberg correction, guardrail evaluation, and a deterministic
ship/hold/roll_back recommendation) runs end to end for a non-commerce
domain — no commerce entity (products, recommendations, product_events,
backend.domains.commerce, backend.llm.client) involved anywhere."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.core.investigation_config import investigation_config_from_adapter
from backend.domains.support.adapter import SupportAdapter
from backend.investigation.pipeline import run_investigation

CATEGORIES = ["billing", "technical", "account_access", "shipping_status", "general_inquiry"]


def _support_investigation_payload(domain: str) -> dict:
    def session(sid: str, version: str, category: str, outcome: str, handle_time: float) -> dict:
        return {
            "external_session_id": sid,
            "external_experiment_id": "support-investigation-exp",
            "agent_version": version,
            "external_user_id": f"user-{sid}",
            "started_at": "2026-02-01T00:00:00",
            "ended_at": "2026-02-01T00:05:00",
            "messages": [{"external_message_id": f"{sid}-m0", "turn_index": 0, "sender": "user", "text": "help", "created_at": "2026-02-01T00:00:00"}],
            "actions": [
                {"external_action_id": f"{sid}-a0", "sequence_index": 0, "action_type": "triage_ticket", "started_at": "2026-02-01T00:00:01", "tool_calls": []},
                {"external_action_id": f"{sid}-a1", "sequence_index": 1, "action_type": "respond", "started_at": "2026-02-01T00:00:06", "tool_calls": []},
            ],
            "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": handle_time}],
            "context": {"ticket_category": category},
        }

    sessions = []
    sid = 0
    for category in CATEGORIES:
        for version in ("v1", "v2"):
            for i in range(12):  # >= MIN_USERS_FOR_TEST per (category, version) cell
                sid += 1
                outcome = "resolved" if i % 4 != 0 else "escalated"
                sessions.append(session(f"inv-{sid}", version, category, outcome, 300.0 + i))

    return {
        "domain": domain,
        "experiments": [{"external_experiment_id": "support-investigation-exp", "name": "Investigation Test", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": sessions,
    }


def test_support_domain_full_investigation_pipeline_runs_end_to_end(api_client, db_engine, support_project_id):
    domain = SupportAdapter.domain
    resp = api_client.post("/api/v1/ingest/sessions", json=_support_investigation_payload(domain), params={"project_id": support_project_id})
    assert resp.status_code == 201

    engine = create_engine(get_database_url())
    adapter = SupportAdapter(engine, project_id=support_project_id)
    config = investigation_config_from_adapter(adapter)

    # Scope to this test's own experiment: other tests in the same pytest
    # session (isolated test database) may also ingest domain="support"
    # data under a different experiment, and analytics_base_df() with no
    # experiment_id spans every experiment for the domain.
    exp = next(e for e in adapter.list_experiments() if e.name == "Investigation Test")
    base_df = adapter.analytics_base_df(experiment_id=exp.experiment_id)
    agent_actions_df = pd.DataFrame(
        {"session_id": [], "sequence_index": pd.Series(dtype="int64"), "action_type": []}
    )
    failure_attributions_wide_df = pd.DataFrame(columns=["session_id"])

    result = run_investigation(base_df, agent_actions_df, failure_attributions_wide_df, config, primary_metric_name="resolution_rate")

    # One segment per registered ticket_category value, no pairwise (only
    # one pre-treatment dimension is registered for this domain).
    assert len(result.scan_rows) == len(CATEGORIES)
    assert result.explored_not_significant_count == len(result.scan_rows) - len(result.findings)

    # Zero registered mechanisms (Stage 3 task 7) -> every finding (if any)
    # carries a non-reportable, empty failure attribution and no dominant mode.
    for finding in result.findings:
        assert finding.dominant_failure_mode is None
        assert finding.failure_attribution.per_mode == []

    guardrail_names = {c.name for c in result.guardrails.checks}
    assert guardrail_names == {"escalation_rate_guardrail"}

    assert result.recommendation.verdict in {"ship", "hold", "roll_back"}
    assert result.recommendation.next_action  # generic or domain-provided, never empty


def test_support_domain_investigation_config_has_no_commerce_dimensions():
    """The InvestigationConfig built from SupportAdapter must reflect only
    this domain's own registered dimension (ticket_category) — never
    commerce's requested_category/platform/persona/etc."""
    from sqlalchemy import create_engine as _create_engine

    from backend.app.db import get_database_url as _get_database_url

    adapter = SupportAdapter(_create_engine(_get_database_url()))
    config = investigation_config_from_adapter(adapter)

    assert config.pre_treatment_dimensions == ["ticket_category"]
    assert set(config.dimension_values) == {"ticket_category"}
    assert config.pairwise_allowlist == []
    assert config.mechanisms == ()
