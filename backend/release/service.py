"""Stage 5 tasks 2-4: release monitoring — running the generic
Investigation engine for one (domain, experiment_id, primary_metric)
triple, translating its deterministic ship/hold/roll_back recommendation
into a persisted release-evaluation row, and reading it back.

This module never imports backend.domains.commerce or
backend.domains.support: every domain-specific input (the DomainAdapter,
the dataframes it produces) is supplied by the caller —
backend.app.domain_registry, the composition root that IS allowed to know
about concrete domains.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from backend.analytics.experiment_results import analyze_all_metrics
from backend.core.adapter import DomainAdapter
from backend.core.investigation_config import investigation_config_from_adapter
from backend.investigation.pipeline import InvestigationResult, run_investigation
from backend.release.models import ReleaseEvaluation

STATUS_BY_VERDICT = {"ship": "SHIP", "hold": "HOLD", "roll_back": "ROLLBACK"}


@dataclass(frozen=True)
class ReleaseEvaluationResult:
    evaluation_id: str
    domain: str
    experiment_id: str
    primary_metric: str
    status: str
    evaluated_at: datetime
    has_negative_segment: bool
    any_guardrail_breach: bool
    primary_reason: str
    next_action: str
    key_metrics: dict = field(default_factory=dict)
    breached_guardrails: list = field(default_factory=list)
    top_findings: list = field(default_factory=list)


def _json_safe(value):
    """Postgres JSONB (and standard JSON) has no NaN/Infinity token —
    Python's json encoder emits one anyway for float('nan')/inf, which
    psycopg then sends verbatim and Postgres rejects. A metric with too
    few eligible rows (e.g. csat_score for a segment with no CSAT-bearing
    sessions) legitimately produces NaN here; store it as null instead of
    letting a rare edge case fail the whole persistence call."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _investigation_to_release_fields(result: InvestigationResult, all_metric_results: list) -> dict:
    key_metrics = {
        r.metric_name: {
            "v1": _json_safe(r.cluster_mean_v1 if r.cluster_mean_v1 is not None else r.session_value_v1),
            "v2": _json_safe(r.cluster_mean_v2 if r.cluster_mean_v2 is not None else r.session_value_v2),
            "p_value": _json_safe(r.p_value),
            "verdict": r.verdict,
        }
        for r in all_metric_results
    }
    key_metrics.setdefault(
        result.primary_metric,
        {
            "v1": _json_safe(result.overall.cluster_mean_v1 if result.overall.cluster_mean_v1 is not None else result.overall.session_value_v1),
            "v2": _json_safe(result.overall.cluster_mean_v2 if result.overall.cluster_mean_v2 is not None else result.overall.session_value_v2),
            "p_value": _json_safe(result.overall.p_value),
            "verdict": result.overall.verdict,
        },
    )

    breached_guardrails = [
        {
            "name": c.name, "severity": c.severity, "v1_value": _json_safe(c.v1_value), "v2_value": _json_safe(c.v2_value),
            "threshold_description": c.threshold_description,
        }
        for c in result.guardrails.checks
        if c.breached
    ]
    top_findings = [
        {
            "segment_label": f.segment_label, "p_value": _json_safe(f.p_value), "excess_contribution": _json_safe(f.excess_contribution),
            "cluster_mean_v1": _json_safe(f.cluster_mean_v1), "cluster_mean_v2": _json_safe(f.cluster_mean_v2),
            "dominant_failure_mode": f.dominant_failure_mode,
        }
        for f in result.findings
    ]
    has_negative_segment = any(f.excess_contribution < 0 for f in result.findings)

    return {
        "key_metrics": key_metrics,
        "breached_guardrails": breached_guardrails,
        "top_findings": top_findings,
        "has_negative_segment": has_negative_segment,
    }


def evaluate_release(
    domain: str,
    experiment_id: str,
    adapter: DomainAdapter,
    primary_metric_name: str,
) -> tuple[InvestigationResult, dict]:
    """Runs the Investigation engine for this (domain, experiment_id,
    primary_metric) — pure computation, no persistence — and returns both
    the raw InvestigationResult (for an API response that wants the full
    findings/scan detail) and the compact release-evaluation fields
    (for persistence and for the release-status summary)."""
    config = investigation_config_from_adapter(adapter)
    base_df = adapter.analytics_base_df(experiment_id=experiment_id)
    agent_actions_df = adapter.agent_actions_df(experiment_id=experiment_id)
    failure_attributions_wide_df = adapter.failure_attributions_wide_df()

    result = run_investigation(base_df, agent_actions_df, failure_attributions_wide_df, config, primary_metric_name=primary_metric_name)
    all_metric_results = analyze_all_metrics(base_df, config.metric_registry, metric_value_columns=config.metric_value_columns)
    fields = _investigation_to_release_fields(result, all_metric_results)
    return result, fields


def persist_release_evaluation(
    engine: Engine,
    domain: str,
    experiment_id: str,
    primary_metric_name: str,
    result: InvestigationResult,
    fields: dict,
) -> ReleaseEvaluationResult:
    evaluation_id = uuid.uuid4()
    evaluated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    status = STATUS_BY_VERDICT[result.recommendation.verdict]

    row = ReleaseEvaluation(
        evaluation_id=evaluation_id,
        domain=domain,
        experiment_id=experiment_id,
        primary_metric=primary_metric_name,
        status=status,
        evaluated_at=evaluated_at,
        has_negative_segment=fields["has_negative_segment"],
        any_guardrail_breach=result.guardrails.any_breach,
        primary_reason=result.recommendation.primary_reason,
        next_action=result.recommendation.next_action,
        key_metrics=fields["key_metrics"],
        breached_guardrails=fields["breached_guardrails"],
        top_findings=fields["top_findings"],
    )
    with OrmSession(engine) as session:
        session.add(row)
        session.commit()

    return ReleaseEvaluationResult(
        evaluation_id=str(evaluation_id),
        domain=domain,
        experiment_id=experiment_id,
        primary_metric=primary_metric_name,
        status=status,
        evaluated_at=evaluated_at,
        has_negative_segment=fields["has_negative_segment"],
        any_guardrail_breach=result.guardrails.any_breach,
        primary_reason=result.recommendation.primary_reason,
        next_action=result.recommendation.next_action,
        key_metrics=fields["key_metrics"],
        breached_guardrails=fields["breached_guardrails"],
        top_findings=fields["top_findings"],
    )


def evaluate_and_persist_release(
    engine: Engine, domain: str, experiment_id: str, adapter: DomainAdapter, primary_metric_name: str
) -> ReleaseEvaluationResult:
    result, fields = evaluate_release(domain, experiment_id, adapter, primary_metric_name)
    persisted = persist_release_evaluation(engine, domain, experiment_id, primary_metric_name, result, fields)

    # Stage 6 task 1: alert generation runs synchronously right after
    # persistence, deterministically, from the same already-computed
    # fields — no separate scheduler, no re-running the Investigation
    # engine a second time.
    from backend.alerts.service import generate_alerts_for_evaluation

    generate_alerts_for_evaluation(engine, domain, experiment_id, persisted.evaluation_id, persisted.status, fields, primary_metric_name)

    return persisted


def _row_to_result(row) -> ReleaseEvaluationResult:
    return ReleaseEvaluationResult(
        evaluation_id=str(row.evaluation_id), domain=row.domain, experiment_id=row.experiment_id,
        primary_metric=row.primary_metric, status=row.status, evaluated_at=row.evaluated_at,
        has_negative_segment=row.has_negative_segment, any_guardrail_breach=row.any_guardrail_breach,
        primary_reason=row.primary_reason, next_action=row.next_action, key_metrics=row.key_metrics,
        breached_guardrails=row.breached_guardrails, top_findings=row.top_findings,
    )


def get_latest_release_status(engine: Engine, domain: str, experiment_id: str) -> ReleaseEvaluationResult | None:
    with OrmSession(engine) as session:
        row = (
            session.query(ReleaseEvaluation)
            .filter(ReleaseEvaluation.domain == domain, ReleaseEvaluation.experiment_id == experiment_id)
            .order_by(ReleaseEvaluation.evaluated_at.desc())
            .first()
        )
    return _row_to_result(row) if row is not None else None


def list_release_history(engine: Engine, domain: str, experiment_id: str, limit: int = 20) -> list[ReleaseEvaluationResult]:
    with OrmSession(engine) as session:
        rows = (
            session.query(ReleaseEvaluation)
            .filter(ReleaseEvaluation.domain == domain, ReleaseEvaluation.experiment_id == experiment_id)
            .order_by(ReleaseEvaluation.evaluated_at.desc())
            .limit(limit)
            .all()
        )
    return [_row_to_result(r) for r in rows]
