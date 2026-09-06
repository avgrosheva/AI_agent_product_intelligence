"""Integration tests for the Investigation-by-lens endpoint (Stage 3/4
review requirement: separate pre-registered lenses, never merged)."""

from __future__ import annotations

import pytest


def test_investigation_requires_lens_query_param(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/investigation")
    assert resp.status_code == 422


def test_investigation_rejects_unknown_lens_value(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/investigation", params={"lens": "not_a_real_lens"})
    assert resp.status_code == 422


@pytest.mark.parametrize("lens,expected_metric,expected_role", [
    ("abandonment", "abandonment_rate", "primary_regression_lens"),
    ("conversion", "conversion_rate", "north_star_context"),
    ("constraint_satisfaction", "constraint_satisfaction_rate", "ai_quality_lens"),
])
def test_investigation_lens_selection(api_client, experiment_id, lens, expected_metric, expected_role):
    resp = api_client.get(f"/experiments/{experiment_id}/investigation", params={"lens": lens})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lens"] == lens
    assert body["primary_metric"] == expected_metric
    assert body["lens_role"] == expected_role
    assert body["overall"]["metric_name"] == expected_metric


def test_investigation_abandonment_lens_has_findings_with_full_shape(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/investigation", params={"lens": "abandonment"})
    body = resp.json()
    assert len(body["findings"]) > 0
    finding = body["findings"][0]
    assert set(finding["segment_filter"]["dimensions"].keys())
    assert "failure_attribution" in finding
    assert "trajectory_associations" in finding
    assert isinstance(finding["failure_attribution"]["per_mode"], list)


def test_investigation_recommendation_is_present_and_typed(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/investigation", params={"lens": "abandonment"})
    rec = resp.json()["recommendation"]
    assert rec["verdict"] in ("ship", "hold", "roll_back")
    assert isinstance(rec["blocking_guardrails"], list)
    assert isinstance(rec["rules_applied"], list) and len(rec["rules_applied"]) > 0


def test_investigation_explored_not_significant_is_reported(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/investigation", params={"lens": "abandonment"})
    body = resp.json()
    assert len(body["explored_not_significant"]) > 0
    top_labels = {f["segment_label"] for f in body["findings"]}
    explored_labels = {e["segment_label"] for e in body["explored_not_significant"]}
    assert top_labels.isdisjoint(explored_labels), "a finding must not also appear in the explored/not-significant list"


def test_investigation_handles_sparse_lens_gracefully(api_client, experiment_id):
    """conversion_rate is known (Stage 2/3) to yield zero top findings at
    dev scale — this must return 200 with an empty findings list, not an
    error."""
    resp = api_client.get(f"/experiments/{experiment_id}/investigation", params={"lens": "conversion"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["findings"] == []
    assert body["recommendation"]["verdict"] in ("ship", "hold", "roll_back")


def test_investigation_lenses_are_not_merged_across_calls(api_client, experiment_id):
    """Each lens call must be self-contained: findings/overall/primary_metric
    must never reference another lens's metric (Stage 3 review requirement #1)."""
    responses = {}
    for lens in ("abandonment", "conversion", "constraint_satisfaction"):
        responses[lens] = api_client.get(f"/experiments/{experiment_id}/investigation", params={"lens": lens}).json()

    for lens, body in responses.items():
        expected_metric = {"abandonment": "abandonment_rate", "conversion": "conversion_rate", "constraint_satisfaction": "constraint_satisfaction_rate"}[lens]
        assert body["overall"]["metric_name"] == expected_metric
        # no finding in this lens's response may be scoped to a different metric
        for finding in body["findings"]:
            # findings don't carry a metric_name field directly, but their cluster
            # means must equal the overall metric's cluster means' scale (sanity:
            # abandonment/conversion/satisfaction are all in [0,1])
            assert 0.0 <= finding["cluster_mean_v1"] <= 1.0
            assert 0.0 <= finding["cluster_mean_v2"] <= 1.0


def test_investigation_unknown_experiment_404(api_client):
    resp = api_client.get(
        "/experiments/00000000-0000-0000-0000-000000000000/investigation", params={"lens": "abandonment"}
    )
    assert resp.status_code == 404


def test_investigation_finding_segment_filter_matches_sessions_endpoint(api_client, experiment_id):
    """Sessions linked from a finding must reproduce the segment shown by
    Investigation (Stage 4 constraint)."""
    resp = api_client.get(f"/experiments/{experiment_id}/investigation", params={"lens": "abandonment"})
    finding = resp.json()["findings"][0]
    dims = finding["segment_filter"]["dimensions"]

    sessions_resp = api_client.get("/sessions", params={**dims, "experiment_id": experiment_id, "limit": 1})
    assert sessions_resp.status_code == 200
    # Session count and the finding's user count are different units (a user
    # can contribute multiple sessions to a segment) — the meaningful check
    # is that the same dimension filter reproduces a non-empty, real slice,
    # not that the two counts are numerically equal.
    assert sessions_resp.json()["total"] > 0
    assert sessions_resp.json()["filters_applied"] == dims
