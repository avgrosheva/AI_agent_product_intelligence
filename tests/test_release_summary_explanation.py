"""Stage 14 tasks 6-7: deterministic explanation text — pure, no
database. Same DecisionSummary fields always produce the same sentence,
built only from already-computed numbers (never invented)."""

from __future__ import annotations

from backend.release.summary import DecisionSummary, generate_explanation_text


def _decision(**overrides) -> DecisionSummary:
    defaults = dict(
        evaluation_id="eval-1", domain="support", experiment_id="exp-1", primary_metric="resolution_rate",
        verdict="SHIP", raw_verdict="SHIP", primary_reason="reason", primary_metric_v1=0.8, primary_metric_v2=0.9,
        primary_metric_delta=0.1, primary_metric_p_value=0.001, breached_guardrails=[], significant_negative_segment_count=0,
        data_quality_status="healthy", data_quality_gated=False, economics_impact=None, confidence="strong",
    )
    defaults.update(overrides)
    return DecisionSummary(**defaults)


def test_rollback_with_guardrail_breach_matches_documented_example_shape():
    decision = _decision(
        verdict="ROLLBACK", raw_verdict="ROLLBACK", primary_metric_delta=-0.6,
        breached_guardrails=[{"name": "escalation_rate_guardrail", "severity": "blocking"}],
    )
    text = generate_explanation_text(decision)
    assert text == "ROLLBACK because resolution_rate decreased by 60.0pp and escalation_rate_guardrail breached its blocking guardrail."


def test_ship_with_no_guardrail_breach():
    decision = _decision(verdict="SHIP", primary_metric_delta=0.109)
    text = generate_explanation_text(decision)
    assert text == "SHIP because resolution_rate increased by 10.9pp."


def test_hold_with_negative_segment_only():
    decision = _decision(verdict="HOLD", raw_verdict="HOLD", primary_metric_delta=0.0, significant_negative_segment_count=2)
    text = generate_explanation_text(decision)
    assert text == "HOLD because resolution_rate was unchanged and 2 significant negative segment(s) were found."


def test_hold_gated_by_critical_data_quality():
    decision = _decision(
        verdict="HOLD", raw_verdict="SHIP", primary_metric_delta=0.1,
        data_quality_status="critical", data_quality_gated=True,
    )
    text = generate_explanation_text(decision)
    assert text == "HOLD because resolution_rate increased by 10.0pp and project data quality is critical, so a confident SHIP is withheld."


def test_unmeasurable_primary_metric():
    decision = _decision(primary_metric_delta=None)
    text = generate_explanation_text(decision)
    assert text == "SHIP because resolution_rate could not be measured."


def test_multiple_blocking_guardrails_are_joined():
    decision = _decision(
        verdict="ROLLBACK", raw_verdict="ROLLBACK", primary_metric_delta=-0.1,
        breached_guardrails=[{"name": "guardrail_a", "severity": "blocking"}, {"name": "guardrail_b", "severity": "blocking"}],
    )
    text = generate_explanation_text(decision)
    assert "guardrail_a and guardrail_b breached their blocking guardrails" in text


def test_non_blocking_guardrail_breach_is_not_mentioned_in_text():
    decision = _decision(
        verdict="SHIP", primary_metric_delta=0.1,
        breached_guardrails=[{"name": "warning_guardrail", "severity": "warning"}],
    )
    text = generate_explanation_text(decision)
    assert "warning_guardrail" not in text


def test_deterministic_across_repeated_calls():
    decision = _decision(verdict="ROLLBACK", raw_verdict="ROLLBACK", primary_metric_delta=-0.3, breached_guardrails=[{"name": "g1", "severity": "blocking"}])
    first = generate_explanation_text(decision)
    second = generate_explanation_text(decision)
    assert first == second
