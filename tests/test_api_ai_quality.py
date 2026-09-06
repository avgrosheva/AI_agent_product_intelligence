"""Integration tests for /ai-quality* endpoints."""

from __future__ import annotations

from backend.llm.client import FAILURE_TAXONOMY


def test_ai_quality_summary_schema(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/ai-quality")
    assert resp.status_code == 200
    body = resp.json()
    modes = {item["failure_mode"] for item in body["failure_mode_distribution"]}
    assert modes == set(FAILURE_TAXONOMY)
    assert body["tool_use_quality"]["tool_calls_per_session_v1"] > 0
    assert body["classifier_provenance"]["is_mock"] is True


def test_ai_quality_trajectory_patterns_pair_frequency_with_outcome(api_client, experiment_id):
    """METRICS.md's 'not an observability platform' stance: every pattern
    row must carry an outcome rate alongside frequency, never frequency alone."""
    resp = api_client.get(f"/experiments/{experiment_id}/ai-quality")
    patterns = resp.json()["trajectory_patterns"]
    assert len(patterns) > 0
    for p in patterns:
        assert "abandonment_rate_v1" in p and "abandonment_rate_v2" in p


def test_ai_quality_unknown_experiment_404(api_client):
    resp = api_client.get("/experiments/00000000-0000-0000-0000-000000000000/ai-quality")
    assert resp.status_code == 404


def test_classifier_evaluation_endpoint(api_client):
    resp = api_client.get("/ai-quality/classifier-evaluation")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provenance"]["classifier_type"] == "rule_based_mock"
    assert body["provenance"]["is_mock"] is True
    assert body["all_acceptance_bars_met"] is True
    priority_classes = {b["failure_mode"] for b in body["acceptance_bars"]}
    assert priority_classes == {"unnecessary_clarification", "wrong_constraint_interpretation"}


def test_classifier_evaluation_never_labeled_as_real_llm_performance(api_client):
    """Stage 3 review requirement #2: a mock classifier's accuracy must
    never be presentable as real LLM classifier performance."""
    body = api_client.get("/ai-quality/classifier-evaluation").json()
    assert body["provenance"]["classifier_type"] != "anthropic"
    assert body["provenance"]["is_mock"] is True


def test_classifier_evaluation_per_class_metrics_shape(api_client):
    body = api_client.get("/ai-quality/classifier-evaluation").json()
    for row in body["per_class_metrics"]:
        assert row["failure_mode"] in FAILURE_TAXONOMY
        assert row["support"] >= 0
