"""Deterministic recommendation rules (Stage 2 review requirement #11;
INVESTIGATION.md SS6)."""

from __future__ import annotations

import inspect

from backend.analytics.experiment_results import MetricResult
from backend.investigation.pipeline import Finding
from backend.investigation.recommend import GuardrailCheck, GuardrailReport, synthesize_recommendation


def _metric_result(v1: float, v2: float, p: float) -> MetricResult:
    return MetricResult(
        metric_name="conversion_rate", segment="all sessions", semantic_class="outcome",
        n_sessions_v1=1000, n_sessions_v2=1000, n_users_v1=300, n_users_v2=300,
        session_value_v1=v1, session_value_v2=v2, cluster_mean_v1=v1, cluster_mean_v2=v2,
        p_value=p, verdict=("significant" if p < 0.05 else "not_significant"),
    )


def _guardrails(any_breach: bool) -> GuardrailReport:
    return GuardrailReport(checks=[GuardrailCheck("p95_latency", 100, 200 if any_breach else 105, "v2 > v1*1.15", any_breach)])


def _finding(ec: float) -> Finding:
    return Finding(
        segment_label="requested_category=monitor", dimensions=("requested_category",),
        n_users_v1=100, n_users_v2=100, cluster_mean_v1=0.2, cluster_mean_v2=0.2 + ec,
        p_value=0.001, effect_size_value=0.3, excess_contribution=ec,
        failure_attribution=None, dominant_failure_mode="wrong_constraint_interpretation",
        trajectory_associations=[],
    )


def test_ship_when_north_star_up_no_guardrail_no_negative_segment():
    result = synthesize_recommendation(_metric_result(0.20, 0.25, 0.001), findings=[], guardrails=_guardrails(False))
    assert result.verdict == "ship"


def test_roll_back_when_north_star_significantly_down():
    result = synthesize_recommendation(_metric_result(0.25, 0.20, 0.001), findings=[], guardrails=_guardrails(False))
    assert result.verdict == "roll_back"


def test_hold_not_roll_back_when_guardrail_breached_but_north_star_only_flat():
    """The documented table's second row ("north star up or flat, but
    guardrail breached") governs this case — a flat (inconclusive) north
    star is not the same as a down one, and must not escalate to
    roll_back on its own. This is the exact shape this project's own
    dataset produces (PRD.md SS2)."""
    result = synthesize_recommendation(_metric_result(0.20, 0.205, 0.60), findings=[], guardrails=_guardrails(True))
    assert result.verdict == "hold"


def test_roll_back_requires_north_star_down_not_merely_flat():
    down = synthesize_recommendation(_metric_result(0.25, 0.20, 0.001), findings=[], guardrails=_guardrails(True))
    flat = synthesize_recommendation(_metric_result(0.20, 0.205, 0.60), findings=[], guardrails=_guardrails(True))
    assert down.verdict == "roll_back"
    assert flat.verdict == "hold"


def test_hold_when_north_star_up_but_guardrail_breached():
    result = synthesize_recommendation(_metric_result(0.20, 0.25, 0.001), findings=[], guardrails=_guardrails(True))
    assert result.verdict == "hold"


def test_hold_when_north_star_flat_and_significant_negative_segment_exists():
    result = synthesize_recommendation(
        _metric_result(0.20, 0.205, 0.60), findings=[_finding(-0.03)], guardrails=_guardrails(False)
    )
    assert result.verdict == "hold"


def test_ship_requires_no_negative_segment_even_if_north_star_up():
    result = synthesize_recommendation(
        _metric_result(0.20, 0.25, 0.001), findings=[_finding(-0.03)], guardrails=_guardrails(False)
    )
    assert result.verdict == "hold"


def test_next_action_matches_dominant_failure_mode_of_top_finding():
    result = synthesize_recommendation(
        _metric_result(0.20, 0.205, 0.60), findings=[_finding(-0.05), _finding(0.01)], guardrails=_guardrails(False)
    )
    assert "constraint" in result.next_action.lower() or "parsing" in result.next_action.lower()


def test_primary_reason_cites_the_largest_absolute_excess_contribution():
    small = _finding(0.01)
    large = _finding(-0.08)
    result = synthesize_recommendation(_metric_result(0.20, 0.205, 0.60), findings=[small, large], guardrails=_guardrails(False))
    assert "requested_category=monitor" in result.primary_reason
    assert "-0.0800" in result.primary_reason or "-0.08" in result.primary_reason


def test_recommendation_verdict_is_never_produced_by_an_llm_call():
    """Structural guard: synthesize_recommendation must not import or call
    any LLM client to decide the verdict (Stage 2 review requirement #11)."""
    from backend.investigation import recommend as recommend_module

    source = inspect.getsource(recommend_module.synthesize_recommendation)
    assert "LLMClient" not in source
    assert ".classify_failure(" not in source
    assert "anthropic" not in source.lower()
