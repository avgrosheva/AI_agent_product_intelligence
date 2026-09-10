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
from backend.core.analysis_window import AnalysisWindow
from backend.core.investigation_config import investigation_config_from_adapter
from backend.economics.compute import EconomicsResult, compute_economics
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
    project_id: str | None = None
    key_metrics: dict = field(default_factory=dict)
    breached_guardrails: list = field(default_factory=list)
    top_findings: list = field(default_factory=list)
    economics: dict | None = None
    raw_status: str = ""
    data_quality_status: str = "healthy"
    data_quality_gated: bool = False
    # Stage 13 task 5: the actual effective window this evaluation used —
    # all three None for a manual, unwindowed evaluation (unchanged from
    # before Stage 13), all three set for a monitoring-job run.
    data_window_start: datetime | None = None
    data_window_end: datetime | None = None
    window_hours: int | None = None


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
            "segment_label": f.segment_label, "dimensions": list(f.dimensions), "p_value": _json_safe(f.p_value),
            "excess_contribution": _json_safe(f.excess_contribution),
            "cluster_mean_v1": _json_safe(f.cluster_mean_v1), "cluster_mean_v2": _json_safe(f.cluster_mean_v2),
            "dominant_failure_mode": f.dominant_failure_mode,
            # Stage 11 task 4: a small, deterministic sample of session ids
            # that illustrate this finding — see
            # backend.investigation.evidence.select_representative_sessions.
            "representative_session_ids": f.representative_session_ids,
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


def _economics_to_dict(economics: EconomicsResult | None) -> dict | None:
    if economics is None:
        return None
    return {
        "cost_per_session_v1": _json_safe(economics.cost_per_session_v1),
        "cost_per_session_v2": _json_safe(economics.cost_per_session_v2),
        "cost_per_success_v1": _json_safe(economics.cost_per_success_v1),
        "cost_per_success_v2": _json_safe(economics.cost_per_success_v2),
        "estimated_incremental_cost_per_session": _json_safe(economics.estimated_incremental_cost_per_session),
        "value_per_success_v1": _json_safe(economics.value_per_success_v1),
        "value_per_success_v2": _json_safe(economics.value_per_success_v2),
        "estimated_business_impact_per_session": _json_safe(economics.estimated_business_impact_per_session),
        "notes": economics.notes,
    }


def evaluate_release(
    domain: str,
    experiment_id: str,
    adapter: DomainAdapter,
    primary_metric_name: str,
    window: AnalysisWindow | None = None,
) -> tuple[InvestigationResult, dict]:
    """Runs the Investigation engine for this (domain, experiment_id,
    primary_metric) — pure computation, no persistence — and returns both
    the raw InvestigationResult (for an API response that wants the full
    findings/scan detail) and the compact release-evaluation fields
    (for persistence and for the release-status summary).

    Stage 13 task 1/3: `window`, when given, is passed straight through
    to the adapter — this function has no filtering logic of its own,
    generic or domain-specific. `None` (a manual evaluation) means the
    full dataset, exactly as before Stage 13 (task 4)."""
    config = investigation_config_from_adapter(adapter)
    base_df = adapter.analytics_base_df(experiment_id=experiment_id, window=window)
    agent_actions_df = adapter.agent_actions_df(experiment_id=experiment_id, window=window)
    failure_attributions_wide_df = adapter.failure_attributions_wide_df()

    result = run_investigation(base_df, agent_actions_df, failure_attributions_wide_df, config, primary_metric_name=primary_metric_name)
    all_metric_results = analyze_all_metrics(base_df, config.metric_registry, metric_value_columns=config.metric_value_columns)
    fields = _investigation_to_release_fields(result, all_metric_results)
    fields["economics"] = _economics_to_dict(compute_economics(base_df, adapter.economics_config()))
    return result, fields


def persist_release_evaluation(
    engine: Engine,
    domain: str,
    experiment_id: str,
    primary_metric_name: str,
    result: InvestigationResult,
    fields: dict,
    project_id: str | None = None,
    data_quality_status: str = "healthy",
    window: AnalysisWindow | None = None,
    window_hours: int | None = None,
) -> ReleaseEvaluationResult:
    evaluation_id = uuid.uuid4()
    evaluated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    raw_status = STATUS_BY_VERDICT[result.recommendation.verdict]
    # Stage 11 task 6: a project whose data quality is "critical" never
    # gets a confident SHIP — the underlying Investigation verdict is
    # still recorded (raw_status), but the status callers act on is
    # downgraded to HOLD so a UI can't present SHIP on suspect data.
    gated = data_quality_status == "critical" and raw_status == "SHIP"
    status = "HOLD" if gated else raw_status
    primary_reason = (
        result.recommendation.primary_reason
        if not gated
        else f"{result.recommendation.primary_reason} (SHIP withheld: project data quality is critical)"
    )

    row = ReleaseEvaluation(
        evaluation_id=evaluation_id,
        domain=domain,
        project_id=project_id,
        experiment_id=experiment_id,
        primary_metric=primary_metric_name,
        status=status,
        raw_status=raw_status,
        data_quality_status=data_quality_status,
        data_quality_gated=gated,
        evaluated_at=evaluated_at,
        has_negative_segment=fields["has_negative_segment"],
        any_guardrail_breach=result.guardrails.any_breach,
        primary_reason=primary_reason,
        next_action=result.recommendation.next_action,
        key_metrics=fields["key_metrics"],
        breached_guardrails=fields["breached_guardrails"],
        top_findings=fields["top_findings"],
        economics=fields.get("economics"),
        data_window_start=window.start if window else None,
        data_window_end=window.end if window else None,
        window_hours=window_hours if window else None,
    )
    with OrmSession(engine) as session:
        session.add(row)
        session.commit()

    return ReleaseEvaluationResult(
        evaluation_id=str(evaluation_id),
        domain=domain,
        project_id=project_id,
        experiment_id=experiment_id,
        primary_metric=primary_metric_name,
        status=status,
        raw_status=raw_status,
        data_quality_status=data_quality_status,
        data_quality_gated=gated,
        evaluated_at=evaluated_at,
        has_negative_segment=fields["has_negative_segment"],
        any_guardrail_breach=result.guardrails.any_breach,
        primary_reason=primary_reason,
        next_action=result.recommendation.next_action,
        key_metrics=fields["key_metrics"],
        breached_guardrails=fields["breached_guardrails"],
        top_findings=fields["top_findings"],
        economics=fields.get("economics"),
        data_window_start=window.start if window else None,
        data_window_end=window.end if window else None,
        window_hours=window_hours if window else None,
    )


def evaluate_and_persist_release(
    engine: Engine,
    domain: str,
    experiment_id: str,
    adapter: DomainAdapter,
    primary_metric_name: str,
    project_id: str | None = None,
    window: AnalysisWindow | None = None,
    window_hours: int | None = None,
) -> ReleaseEvaluationResult:
    """Stage 13: `window`/`window_hours` are the ONLY new parameters this
    function gained — a manual call (the on-demand release-evaluations
    API endpoint) never passes them, so its behavior is byte-identical to
    before Stage 13 (task 4). backend.monitoring.service.run_monitoring_job
    is the one caller that does, for a config with window_hours set."""
    result, fields = evaluate_release(domain, experiment_id, adapter, primary_metric_name, window=window)

    data_quality_status = "healthy"
    if project_id is not None:
        from backend.quality.service import compute_data_quality_report

        # Stage 13 task 7: the SAME window narrows only the checks that
        # describe this evaluation's own data (missing outcome/metric
        # coverage, arm balance, sessions without version) — freshness and
        # connector-health checks stay global regardless, inside
        # compute_data_quality_report itself.
        data_quality_status = compute_data_quality_report(engine, project_id, domain, window=window).status

    persisted = persist_release_evaluation(
        engine, domain, experiment_id, primary_metric_name, result, fields, project_id=project_id,
        data_quality_status=data_quality_status, window=window, window_hours=window_hours,
    )

    # Stage 6 task 1: alert generation runs synchronously right after
    # persistence, deterministically, from the same already-computed
    # fields — no separate scheduler, no re-running the Investigation
    # engine a second time.
    from backend.alerts.service import generate_alerts_for_evaluation

    generate_alerts_for_evaluation(engine, domain, experiment_id, persisted.evaluation_id, persisted.status, fields, primary_metric_name, project_id=project_id)

    # Stage 12 task 2: notifications, same synchronous-right-after-
    # persistence pattern as alerts above, from the SAME already-computed
    # `persisted` result — no new decision logic.
    from backend.notifications.service import dispatch_release_notifications

    dispatch_release_notifications(engine, project_id, persisted)

    return persisted


def _row_to_result(row) -> ReleaseEvaluationResult:
    return ReleaseEvaluationResult(
        evaluation_id=str(row.evaluation_id), domain=row.domain, project_id=row.project_id, experiment_id=row.experiment_id,
        primary_metric=row.primary_metric, status=row.status, evaluated_at=row.evaluated_at,
        has_negative_segment=row.has_negative_segment, any_guardrail_breach=row.any_guardrail_breach,
        primary_reason=row.primary_reason, next_action=row.next_action, key_metrics=row.key_metrics,
        breached_guardrails=row.breached_guardrails, top_findings=row.top_findings, economics=row.economics,
        raw_status=row.raw_status, data_quality_status=row.data_quality_status, data_quality_gated=row.data_quality_gated,
        data_window_start=row.data_window_start, data_window_end=row.data_window_end, window_hours=row.window_hours,
    )


def get_release_evaluation_by_id(engine: Engine, evaluation_id: str, project_id: str | None = None) -> ReleaseEvaluationResult | None:
    """Stage 11 task 3: the evidence endpoint looks up one specific past
    evaluation by id (not just "the latest") — scoped by project_id like
    every other release-evaluation read, so a caller can never fetch
    another project's evaluation by guessing its id."""
    with OrmSession(engine) as session:
        query = session.query(ReleaseEvaluation).filter(ReleaseEvaluation.evaluation_id == uuid.UUID(evaluation_id))
        if project_id is not None:
            query = query.filter(ReleaseEvaluation.project_id == project_id)
        row = query.first()
    return _row_to_result(row) if row is not None else None


def get_latest_release_status(engine: Engine, domain: str, experiment_id: str, project_id: str | None = None) -> ReleaseEvaluationResult | None:
    with OrmSession(engine) as session:
        query = session.query(ReleaseEvaluation).filter(ReleaseEvaluation.domain == domain, ReleaseEvaluation.experiment_id == experiment_id)
        if project_id is not None:
            query = query.filter(ReleaseEvaluation.project_id == project_id)
        row = query.order_by(ReleaseEvaluation.evaluated_at.desc()).first()
    return _row_to_result(row) if row is not None else None


def list_release_history(engine: Engine, domain: str, experiment_id: str, project_id: str | None = None, limit: int = 20) -> list[ReleaseEvaluationResult]:
    with OrmSession(engine) as session:
        query = session.query(ReleaseEvaluation).filter(ReleaseEvaluation.domain == domain, ReleaseEvaluation.experiment_id == experiment_id)
        if project_id is not None:
            query = query.filter(ReleaseEvaluation.project_id == project_id)
        rows = query.order_by(ReleaseEvaluation.evaluated_at.desc()).limit(limit).all()
    return [_row_to_result(r) for r in rows]
