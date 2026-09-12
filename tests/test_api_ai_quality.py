"""Integration tests for /ai-quality/classifier-evaluation.

Security fix: this file used to also cover GET
/experiments/{experiment_id}/ai-quality, removed from
backend.app.routers.ai_quality because it had no project/org ownership
check (see that module's docstring). The equivalent, project-scoped
data is covered by tests/test_generic_domain_api.py's
test_generic_ai_quality_endpoint_on_commerce/_on_support against GET
/api/v1/domains/{domain}/experiments/{experiment_id}/ai-quality."""

from __future__ import annotations

from backend.llm.client import FAILURE_TAXONOMY


def test_classifier_evaluation_endpoint(api_client):
    """The old exclusive-classifier evaluation summary was archived when
    the hybrid multi-label redesign shipped (it evaluated a taxonomy this
    pipeline no longer produces), so THIS shape (per_class_metrics/
    all_acceptance_bars_met — the deprecated architecture's fields) still
    honestly reports "not evaluated" rather than presenting stale/
    mismatched numbers. Stage 16: the current architecture's own
    evaluation is surfaced separately via hybrid_evaluation — see
    test_classifier_evaluation_includes_current_hybrid_benchmark."""
    resp = api_client.get("/ai-quality/classifier-evaluation")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provenance"]["classifier_type"] == "rule_based_mock"
    assert body["provenance"]["is_mock"] is True
    assert body["all_acceptance_bars_met"] is None
    assert body["per_class_metrics"] == []


def test_classifier_evaluation_never_labeled_as_real_llm_performance(api_client):
    """Stage 3 review requirement #2: a mock classifier's accuracy must
    never be presentable as real LLM classifier performance."""
    body = api_client.get("/ai-quality/classifier-evaluation").json()
    assert body["provenance"]["classifier_type"] != "real_llm"
    assert body["provenance"]["is_mock"] is True


def test_classifier_evaluation_per_class_metrics_shape(api_client):
    body = api_client.get("/ai-quality/classifier-evaluation").json()
    for row in body["per_class_metrics"]:
        assert row["failure_mode"] in FAILURE_TAXONOMY
        assert row["support"] >= 0


def test_classifier_evaluation_includes_current_hybrid_benchmark(api_client):
    """Stage 16: the CURRENT architecture's own held-out benchmark
    (reports/final/semantic_holdout_200_summary.json, produced by
    scripts.run_hybrid_benchmark --subset new_holdout) is surfaced here,
    independent of the deprecated exclusive-classifier fields tested
    above — this is what closes the gap test_classifier_evaluation_endpoint
    documents (that shape staying honestly "not evaluated" forever)."""
    body = api_client.get("/ai-quality/classifier-evaluation").json()
    hybrid = body["hybrid_evaluation"]
    assert hybrid is not None
    assert hybrid["subset"] == "new_holdout"
    assert hybrid["provider"] == "openrouter"
    assert {d["failure_mode"] for d in hybrid["deterministic_detectors"]} == {"retrieval_failure", "poor_ranking", "wrong_tool_selection"}
    assert {s["failure_mode"] for s in hybrid["semantic_metrics"]} == {
        "unnecessary_clarification", "wrong_constraint_interpretation", "unsupported_product_claim",
    }
    for d in hybrid["deterministic_detectors"]:
        assert 0.0 <= d["f1"] <= 1.0
    assert 0.0 <= hybrid["semantic_macro_f1"] <= 1.0
    assert 0.0 <= hybrid["semantic_hamming_loss"] <= 1.0
    assert "correctly-implemented detector" in hybrid["deterministic_detectors_note"]
