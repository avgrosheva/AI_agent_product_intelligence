"""Stage 6 task 1: deterministic alert rule logic
(backend.alerts.rules.evaluate_alert_rules), exercised with synthetic
status/fields dicts — same crafted-input pattern already used for
backend.investigation.recommend.synthesize_recommendation in
tests/test_investigation_recommend.py — so this suite never depends on
engineering a real dataset to reach a specific statistical outcome."""

from __future__ import annotations

from backend.alerts.rules import evaluate_alert_rules


def _fields(breached_guardrails=None, top_findings=None, has_negative_segment=False):
    return {
        "key_metrics": {},
        "breached_guardrails": breached_guardrails or [],
        "top_findings": top_findings or [],
        "has_negative_segment": has_negative_segment,
    }


def test_no_alerts_on_ship_with_no_breach():
    alerts = evaluate_alert_rules("SHIP", _fields(), "conversion_rate")
    assert alerts == []


def test_rollback_always_fires_a_critical_alert():
    alerts = evaluate_alert_rules("ROLLBACK", _fields(), "conversion_rate")
    assert len(alerts) == 1
    assert alerts[0].rule == "rollback"
    assert alerts[0].severity == "critical"
    assert alerts[0].dedup_key == "rollback"


def test_blocking_guardrail_breach_fires_one_alert_per_breached_blocking_guardrail():
    fields = _fields(
        breached_guardrails=[
            {"name": "p95_latency", "severity": "blocking", "v1_value": 100, "v2_value": 200, "threshold_description": "v2 > v1 x 1.15"},
            {"name": "cost_per_session", "severity": "blocking", "v1_value": 1.0, "v2_value": 2.0, "threshold_description": "v2 > v1 x 1.2"},
        ]
    )
    alerts = evaluate_alert_rules("HOLD", fields, "conversion_rate")
    guardrail_alerts = [a for a in alerts if a.rule == "blocking_guardrail_breach"]
    assert {a.related_guardrail for a in guardrail_alerts} == {"p95_latency", "cost_per_session"}
    assert all(a.severity == "critical" for a in guardrail_alerts)
    assert len({a.dedup_key for a in guardrail_alerts}) == 2  # distinct dedup keys per guardrail


def test_warning_severity_guardrail_breach_does_not_fire_the_blocking_rule():
    fields = _fields(breached_guardrails=[{"name": "soft_metric", "severity": "warning", "v1_value": 1, "v2_value": 2, "threshold_description": "x"}])
    alerts = evaluate_alert_rules("HOLD", fields, "conversion_rate")
    assert alerts == []


def test_hold_with_negative_segment_fires_a_warning_alert():
    fields = _fields(
        top_findings=[{"segment_label": "platform=android", "excess_contribution": -0.05}],
        has_negative_segment=True,
    )
    alerts = evaluate_alert_rules("HOLD", fields, "conversion_rate")
    assert len(alerts) == 1
    assert alerts[0].rule == "hold_negative_segment"
    assert alerts[0].severity == "warning"
    assert alerts[0].related_finding == "platform=android"


def test_hold_without_negative_segment_or_breach_fires_nothing():
    alerts = evaluate_alert_rules("HOLD", _fields(has_negative_segment=False), "conversion_rate")
    assert alerts == []


def test_ship_never_fires_hold_or_rollback_rules_even_with_negative_segment_field_set():
    """has_negative_segment/breached_guardrails describe the evaluation
    that produced this status — a SHIP status means neither actually
    blocked the recommendation (e.g. a warning-only guardrail), so no
    rollback/hold-specific alert should fire regardless."""
    fields = _fields(top_findings=[{"segment_label": "x", "excess_contribution": -0.01}], has_negative_segment=True)
    alerts = evaluate_alert_rules("SHIP", fields, "conversion_rate")
    assert alerts == []


def test_rollback_and_guardrail_breach_can_both_fire_together():
    fields = _fields(breached_guardrails=[{"name": "tool_error_rate", "severity": "blocking", "v1_value": 0.01, "v2_value": 0.05, "threshold_description": "x"}])
    alerts = evaluate_alert_rules("ROLLBACK", fields, "conversion_rate")
    rules_fired = {a.rule for a in alerts}
    assert rules_fired == {"rollback", "blocking_guardrail_breach"}
