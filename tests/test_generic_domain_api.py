"""Stage 5 task 1/7: the generic, domain-parametrized API
(/api/v1/domains/{domain}/...) proven against BOTH domains through the
same endpoints — no per-domain branching in the router, no commerce
default. Commerce uses the dev-scale fixture data conftest.py already
loads; support ingests its own small fixture through the Stage 3 ingestion
API, exactly like tests/test_support_domain_adapter.py."""

from __future__ import annotations

CATEGORIES = ["billing", "technical", "account_access", "shipping_status", "general_inquiry"]


def _support_payload(domain: str, tag: str) -> dict:
    def session(sid: str, version: str, outcome: str) -> dict:
        return {
            "external_session_id": sid,
            "external_experiment_id": f"generic-api-exp-{tag}",
            "agent_version": version,
            "external_user_id": f"user-{sid}",
            "started_at": "2026-03-01T00:00:00",
            "ended_at": "2026-03-01T00:05:00",
            "messages": [{"external_message_id": f"{sid}-m0", "turn_index": 0, "sender": "user", "text": "help", "created_at": "2026-03-01T00:00:00"}],
            "actions": [{"external_action_id": f"{sid}-a0", "sequence_index": 0, "action_type": "triage_ticket", "started_at": "2026-03-01T00:00:01", "tool_calls": []}],
            "outcome": {"label": outcome, "metrics": []},
            "metrics": [{"name": "handle_time_seconds", "value": 300.0}],
            "context": {"ticket_category": "billing"},
        }

    sessions = []
    for i in range(12):
        sessions.append(session(f"api-{tag}-v1-{i}", "v1", "resolved" if i % 3 else "escalated"))
    for i in range(12):
        sessions.append(session(f"api-{tag}-v2-{i}", "v2", "resolved"))
    return {
        "domain": domain,
        "experiments": [{"external_experiment_id": f"generic-api-exp-{tag}", "name": f"Generic API Test {tag}", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": sessions,
    }


def _ingest_support_fixture(api_client, tag: str, support_project_id: str) -> str:
    from backend.domains.support.adapter import SupportAdapter

    resp = api_client.post("/api/v1/ingest/sessions", json=_support_payload(SupportAdapter.domain, tag), params={"project_id": support_project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]
    exp = next(e for e in experiments if e["name"] == f"Generic API Test {tag}")
    return exp["experiment_id"]


def test_list_domains_includes_both(api_client):
    resp = api_client.get("/api/v1/domains")
    assert resp.status_code == 200
    assert set(resp.json()) == {"commerce", "support"}


def test_unknown_domain_is_404(api_client):
    resp = api_client.get("/api/v1/domains/nonexistent/experiments")
    assert resp.status_code == 404


def test_generic_experiments_endpoint_on_commerce(api_client, experiment_id):
    resp = api_client.get("/api/v1/domains/commerce/experiments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "commerce"
    assert any(e["experiment_id"] == experiment_id for e in body["experiments"])


def test_generic_experiments_endpoint_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "list", support_project_id)
    resp = api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "support"
    assert any(e["experiment_id"] == exp_id for e in body["experiments"])


def test_generic_experiments_list_includes_north_star_fields(api_client, experiment_id):
    """Stage 16: the Overview screen's portfolio card needs a north-star
    number and status chip per experiment, generalized from the legacy
    commerce-only list_experiments (backend.app.routers.experiments) to
    read this project's own configured primary_metric instead of a
    hardcoded "conversion_rate". Whether or not this project has
    configured one yet is state this test doesn't control (mutating it
    would leak into every other test sharing this session-scoped
    project), so this only pins the one invariant that holds either way:
    a north-star number is present exactly when session counts are."""
    resp = api_client.get("/api/v1/domains/commerce/experiments")
    assert resp.status_code == 200
    exp = next(e for e in resp.json()["experiments"] if e["experiment_id"] == experiment_id)
    assert exp["status_chip"] in {"ambiguous_investigate", "no_regression_detected", "not_yet_investigated"}
    assert (exp["north_star_metric"] is None) == (exp["n_sessions"] is None)


def test_generic_experiments_status_chip_flags_a_lower_is_better_regression(api_client, experiment_id, commerce_project_id):
    """Stage 16: a positive v2-vs-v1 delta is only "improvement" for a
    higher-is-better metric -- for abandonment_rate (lower-is-better),
    v2 significantly HIGHER than v1 is a regression and must set
    status_chip to "ambiguous_investigate", not "no_regression_detected"
    (backend.app.routers.experiments._status_chip's direction param;
    same bug class as the release/summary.py primary-metric-wording fix)."""
    put_resp = api_client.put(f"/api/v1/domains/commerce/config?project_id={commerce_project_id}", json={"primary_metric": "abandonment_rate"})
    assert put_resp.status_code == 200
    try:
        resp = api_client.get(f"/api/v1/domains/commerce/experiments?project_id={commerce_project_id}")
        assert resp.status_code == 200
        exp = next(e for e in resp.json()["experiments"] if e["experiment_id"] == experiment_id)
        assert exp["north_star_metric"]["metric_name"] == "abandonment_rate"
        assert exp["north_star_metric"]["cluster_mean_v2"] > exp["north_star_metric"]["cluster_mean_v1"]
        assert exp["north_star_metric"]["verdict"] == "significant"
        assert exp["status_chip"] == "ambiguous_investigate"
    finally:
        api_client.put(f"/api/v1/domains/commerce/config?project_id={commerce_project_id}", json={"primary_metric": None})


def test_generic_metrics_endpoint_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/metrics")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    assert any(m["metric_name"] == "conversion_rate" for m in metrics)


def test_generic_metrics_endpoint_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "metrics", support_project_id)
    resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/metrics?project_id={support_project_id}")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    names = {m["metric_name"] for m in metrics}
    assert "resolution_rate" in names
    # ticket_category is pre_treatment/non-inferential -> never in this table
    assert "ticket_category" not in names


def test_generic_guardrails_endpoint_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/guardrails")
    assert resp.status_code == 200
    body = resp.json()
    assert {c["name"] for c in body["checks"]} == {"p95_latency", "tool_error_rate", "cost_per_session"}


def test_generic_guardrails_endpoint_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "guardrails", support_project_id)
    resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/guardrails?project_id={support_project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert {c["name"] for c in body["checks"]} == {"escalation_rate_guardrail"}
    assert body["checks"][0]["metric"] == "escalation_rate"


def test_generic_investigation_requires_primary_metric_query_param(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/investigation")
    assert resp.status_code == 422


def test_generic_investigation_rejects_unknown_metric(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/investigation?primary_metric=not_a_real_metric")
    assert resp.status_code == 422


def test_generic_investigation_endpoint_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/investigation?primary_metric=abandonment_rate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation"]["verdict"] in {"ship", "hold", "roll_back"}
    assert body["primary_metric"] == "abandonment_rate"


def test_generic_investigation_endpoint_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "investigation", support_project_id)
    resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/investigation?primary_metric=resolution_rate&project_id={support_project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation"]["verdict"] in {"ship", "hold", "roll_back"}
    # zero registered mechanisms -> every finding has no dominant failure mode
    for finding in body["findings"]:
        assert finding["dominant_failure_mode"] is None


def test_generic_mechanisms_endpoint_on_commerce(api_client):
    resp = api_client.get("/api/v1/domains/commerce/mechanisms")
    assert resp.status_code == 200
    names = {m["name"] for m in resp.json()["mechanisms"]}
    assert "retrieval_failure" in names and "unnecessary_clarification" in names


def test_generic_mechanisms_endpoint_on_support_is_empty():
    from backend.domains.support.mechanisms import SUPPORT_MECHANISMS

    assert SUPPORT_MECHANISMS.all_names == ()


def test_generic_sessions_list_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "commerce"
    assert len(body["items"]) == 5
    assert body["items"][0]["agent_version"] in ("v1", "v2")


def test_generic_sessions_list_and_detail_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "sessions", support_project_id)
    # Scoped to this test's own experiment: other tests sharing the same
    # support_project_id (one project per domain, by design) also ingest
    # sessions there, and an unscoped list spans every experiment in the
    # project — sorted by started_at, so a differently-dated fixture from
    # another test could otherwise land in this page instead of this
    # test's own "triage_ticket" sessions.
    resp = api_client.get(f"/api/v1/domains/support/sessions?experiment_id={exp_id}&limit=3&project_id={support_project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 3
    sid = body["items"][0]["session_id"]

    detail = api_client.get(f"/api/v1/domains/support/sessions/{sid}?project_id={support_project_id}")
    assert detail.status_code == 200
    d = detail.json()
    assert d["domain"] == "support"
    assert d["action_sequence"] == ["triage_ticket"]


def test_generic_sessions_list_filters_by_segment_dimension_on_commerce(api_client, experiment_id):
    """Stage 16: the same dimension vocabulary Investigation findings use
    (adapter.segment_dimensions()) now filters the generic sessions list
    too, so a "View sessions" link built from a Finding's segment filters
    correctly -- for any domain, not just commerce's hardcoded columns."""
    unfiltered = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&limit=1").json()
    assert unfiltered["total"] > 0

    filtered = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&platform=android&limit=1")
    assert filtered.status_code == 200
    assert filtered.json()["total"] <= unfiltered["total"]

    # An unregistered query param (not one of this domain's segment
    # dimensions) is silently ignored, not treated as a filter.
    ignored = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&not_a_real_dimension=xyz&limit=1")
    assert ignored.status_code == 200
    assert ignored.json()["total"] == unfiltered["total"]


def test_generic_sessions_list_filters_by_outcome_on_commerce(api_client, experiment_id):
    """Stage 17 task 3: outcome is a domain-agnostic filter (every
    domain's analytics_base_df carries some outcome/outcome_label
    column), unlike the dimension-specific filters above."""
    all_sessions = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&limit=1").json()
    abandoned = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&outcome=abandoned&limit=5")
    assert abandoned.status_code == 200
    body = abandoned.json()
    assert 0 < body["total"] <= all_sessions["total"]
    assert all(item["outcome"] == "abandoned" for item in body["items"])


def test_generic_sessions_list_filters_by_time_range_on_commerce(api_client, experiment_id):
    unfiltered = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&limit=1").json()
    assert unfiltered["total"] > 0
    # A window in the far future excludes every session.
    empty = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&started_after=2099-01-01T00:00:00&limit=1")
    assert empty.status_code == 200
    assert empty.json()["total"] == 0
    # started_before far in the past also excludes everything; far in the
    # future includes everything already in the dataset.
    everything = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&started_before=2099-01-01T00:00:00&limit=1")
    assert everything.status_code == 200
    assert everything.json()["total"] == unfiltered["total"]


def test_generic_sessions_list_filters_by_detected_mechanism_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&detected_mechanism=unnecessary_clarification&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 0
    assert all('unnecessary_clarification' in item["detected_mechanisms"] for item in body["items"])


def test_generic_sessions_list_filters_by_review_status_on_commerce(api_client, experiment_id, db_engine):
    from sqlalchemy import text

    # The dev-scale database persists across the whole pytest session and
    # several OTHER test files legitimately submit their own "confirmed"
    # reviews against commerce sessions (test_attribution_review.py,
    # test_rbac.py, test_release_summary_api.py) -- asserting a global
    # count of zero confirmed reviews is therefore order-dependent and
    # false whenever this test runs after any of them. Instead, this test
    # creates and confirms its own review for a specific session and
    # proves THAT session moves from the unreviewed bucket to the
    # confirmed one, which holds regardless of what any other test left
    # behind.
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT sfa.session_id::text AS session_id, sfa.failure_mode::text AS failure_mode "
                "FROM session_failure_attributions sfa "
                "JOIN sessions s ON s.session_id = sfa.session_id "
                "LEFT JOIN attribution_reviews ar ON ar.session_id = sfa.session_id::text AND ar.failure_mode::text = sfa.failure_mode::text AND ar.domain = 'commerce' "
                "WHERE sfa.detected = true AND ar.session_id IS NULL AND s.experiment_id::text = :eid "
                "ORDER BY sfa.session_id, sfa.failure_mode LIMIT 1"
            ),
            {"eid": experiment_id},
        ).mappings().first()
    assert row is not None, "expected at least one detected, never-reviewed commerce attribution in the dev-scale fixture"
    session_id, failure_mode = row["session_id"], row["failure_mode"]

    review_resp = api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review", json={"decision": "confirmed"}
    )
    assert review_resp.status_code == 201

    unreviewed = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&review_status=unreviewed&limit=500")
    assert unreviewed.status_code == 200
    assert session_id not in {s["session_id"] for s in unreviewed.json()["items"]}

    confirmed = api_client.get(f"/api/v1/domains/commerce/sessions?experiment_id={experiment_id}&review_status=confirmed&limit=500")
    assert confirmed.status_code == 200
    assert session_id in {s["session_id"] for s in confirmed.json()["items"]}


def test_generic_segment_dimensions_endpoint_on_commerce(api_client):
    resp = api_client.get("/api/v1/domains/commerce/segment-dimensions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "commerce"
    assert "platform" in body["dimensions"]
    assert "android" in body["dimensions"]["platform"]


def test_generic_segment_dimensions_endpoint_on_support(api_client, support_project_id):
    resp = api_client.get(f"/api/v1/domains/support/segment-dimensions?project_id={support_project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "support"
    assert "ticket_category" in body["dimensions"]


def test_generic_session_detail_404_for_unknown_id(api_client, support_project_id):
    resp = api_client.get(f"/api/v1/domains/support/sessions/00000000-0000-0000-0000-000000000000?project_id={support_project_id}")
    assert resp.status_code == 404


def test_generic_funnel_endpoint_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/funnel")
    assert resp.status_code == 200
    body = resp.json()
    assert body["applicable"] is True
    assert {s["agent_version"] for s in body["series"]} == {"v1", "v2"}
    stages = [pt["stage"] for pt in body["series"][0]["stages"]]
    assert stages == ["impression", "click", "cart", "purchase"]
    assert body["series"][0]["stages"][0]["conversion_from_previous"] is None


def test_generic_funnel_endpoint_on_support_is_not_applicable(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "funnel", support_project_id)
    resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/funnel?project_id={support_project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["applicable"] is False
    assert body["series"] == []


def test_generic_ai_quality_endpoint_on_commerce(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/ai-quality")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "commerce"
    names = {p["failure_mode"] for p in body["failure_mechanism_prevalence"]}
    assert "retrieval_failure" in names and "unnecessary_clarification" in names
    assert body["tool_use_quality"]["tool_calls_per_session_v1"] is not None
    assert body["tool_use_quality"]["tool_error_rate_v1"] is not None


def test_generic_ai_quality_endpoint_on_support(api_client, support_project_id):
    exp_id = _ingest_support_fixture(api_client, "aiquality", support_project_id)
    resp = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/ai-quality?project_id={support_project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "support"
    # zero registered mechanisms (test_generic_mechanisms_endpoint_on_support_is_empty) -> empty prevalence
    assert body["failure_mechanism_prevalence"] == []
    assert body["tool_use_quality"]["tool_calls_per_session_v1"] is not None
    # support's ingested data has no per-arm tool error rate column at all
    assert body["tool_use_quality"]["tool_error_rate_v1"] is None
