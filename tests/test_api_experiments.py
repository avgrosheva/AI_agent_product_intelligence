"""Integration tests for /experiments* endpoints."""

from __future__ import annotations


def test_list_experiments_returns_valid_summary(api_client):
    resp = api_client.get("/experiments")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["experiments"]) >= 1
    exp = body["experiments"][0]
    assert exp["status_chip"] in ("ambiguous_investigate", "no_regression_detected", "not_yet_investigated")
    assert exp["north_star_metric"]["metric_name"] == "conversion_rate"
    assert exp["n_sessions"] > 0
    assert exp["n_users"] > 0


def test_get_experiment_detail(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["experiment_id"] == experiment_id
    assert body["n_sessions_v1"] > 0 and body["n_sessions_v2"] > 0
    assert body["n_users_v1"] > 0 and body["n_users_v2"] > 0


def test_get_unknown_experiment_returns_404(api_client):
    resp = api_client.get("/experiments/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert "error_code" in resp.json()


def test_malformed_experiment_id_returns_404_not_500(api_client):
    resp = api_client.get("/experiments/not-a-uuid")
    assert resp.status_code == 404


def test_experiment_metrics_schema_completeness(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/metrics")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    assert len(metrics) > 10
    required_fields = {
        "metric_name", "segment", "semantic_class", "is_descriptive", "is_inferential",
        "n_sessions_v1", "n_sessions_v2", "session_value_v1", "session_value_v2",
        "n_users_v1", "n_users_v2", "verdict",
    }
    for m in metrics:
        assert required_fields.issubset(m.keys())
        assert m["semantic_class"] in ("pre_treatment", "treatment", "post_treatment_mechanism", "outcome", "economic_outcome")
        assert m["verdict"] in ("significant", "not_significant", "insufficient_evidence")


def test_experiment_metrics_preserves_descriptive_vs_inferential_distinction(api_client, experiment_id):
    """A metric with insufficient evidence must not carry a fabricated
    p-value/CI (Stage 2/3 review causal/statistical-honesty requirement)."""
    resp = api_client.get(f"/experiments/{experiment_id}/metrics")
    metrics = resp.json()["metrics"]
    for m in metrics:
        if m["verdict"] == "insufficient_evidence":
            assert m["p_value"] is None
        # descriptive value always present regardless of inferential status
        assert m["session_value_v1"] is not None
        assert m["session_value_v2"] is not None


def test_experiment_metrics_semantic_class_filter(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/metrics", params={"semantic_class": "economic_outcome"})
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    assert len(metrics) > 0
    assert all(m["semantic_class"] == "economic_outcome" for m in metrics)


def test_experiment_funnel(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/funnel")
    assert resp.status_code == 200
    funnel = resp.json()["funnel"]
    assert {f["agent_version"] for f in funnel} == {"v1", "v2"}
    for step in funnel:
        assert step["n_impression"] >= step["n_click"] >= step["n_cart"] >= step["n_purchase"]


def test_experiment_guardrails(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/guardrails")
    assert resp.status_code == 200
    body = resp.json()
    names = {c["name"] for c in body["checks"]}
    assert names == {"p95_latency", "tool_error_rate", "cost_per_session"}
    assert body["any_breach"] == any(c["breached"] for c in body["checks"])
