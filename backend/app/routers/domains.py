"""Stage 5 task 1: generic, domain-parametrized API. Every endpoint here
takes a `domain` path parameter, resolves a DomainAdapter through
backend.app.domain_registry (the only module in this file's import graph
allowed to know about backend.domains.commerce/backend.domains.support),
and computes its response through backend.core / backend.analytics /
backend.investigation / backend.release — the same generic engine the
commerce-only routers (experiments.py, investigation.py, sessions.py,
ai_quality.py) already use, just without a commerce default baked in.

Mounted under /api/v1/domains/{domain}/... so it cannot collide with the
existing commerce-only routes (which stay exactly as they were — Stage 5
task 6: commerce behavior unchanged).

Stage 7 tasks 2-3: every endpoint now requires authentication AND
resolves a ProjectContext (backend.app.auth_deps) — the caller's project
for this domain, checked against their organization membership — so a
DomainAdapter here is always built bound to that project_id. Mutating
endpoints additionally require the "analyst" role or higher.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.analytics.experiment_results import analyze_all_metrics
from backend.app.auth_deps import CurrentUser, ProjectContext, get_current_user, get_project_context, require_role
from backend.app.domain_registry import available_domains, get_adapter, get_engine
from backend.app.investigation_serialization import finding_to_schema
from backend.app.schemas.common import metric_result_to_schema
from backend.app.schemas.domain_generic import (
    GenericExperimentListResponse,
    GenericExperimentSummary,
    GenericFailureAttributionSchema,
    GenericGuardrailCheckSchema,
    GenericGuardrailResponse,
    GenericInvestigationResponse,
    GenericMetricTableResponse,
    GenericSessionDetailResponse,
    GenericSessionListResponse,
    GenericSessionSummary,
    GenericToolCallSchema,
    MechanismListResponse,
    MechanismSchema,
    DataQualityReportResponse,
    LinkedMechanismSchema,
    NegativeSegmentEvidenceSchema,
    ReleaseEvaluationSchema,
    ReleaseEvidenceResponse,
    ReleaseHistoryResponse,
    SessionEvidenceSchema,
)
from backend.app.schemas.investigation import ExploredSegmentSummary, RecommendationSchema
from backend.core.adapter import DomainAdapter
from backend.core.guardrails import evaluate_guardrails
from backend.core.investigation_config import investigation_config_from_adapter
from backend.investigation.pipeline import run_investigation
from backend.quality.service import compute_data_quality_report
from backend.release.evidence import build_release_evidence
from backend.release.service import evaluate_and_persist_release, get_latest_release_status, get_release_evaluation_by_id, list_release_history
from backend.review.service import get_reviews_for_session

router = APIRouter(prefix="/api/v1/domains", tags=["generic-domain-api"])


def _experiment_or_404(adapter: DomainAdapter, experiment_id: str) -> GenericExperimentSummary:
    for exp in adapter.list_experiments():
        if exp.experiment_id == experiment_id:
            return GenericExperimentSummary(
                experiment_id=exp.experiment_id, name=exp.name, control_version=exp.control_version,
                treatment_version=exp.treatment_version, start_date=exp.start_date, end_date=exp.end_date,
            )
    raise HTTPException(status_code=404, detail=f"No experiment with id '{experiment_id}' in domain '{adapter.domain}'")


def _validate_primary_metric(adapter: DomainAdapter, primary_metric: str) -> None:
    implemented = {m.name for m in adapter.metric_definitions() if m.implemented and m.is_inferential}
    if primary_metric not in implemented:
        raise HTTPException(
            status_code=422,
            detail=f"'{primary_metric}' is not an implemented, inferential metric for domain '{adapter.domain}'. Available: {sorted(implemented)}",
        )


@router.get("", response_model=list[str])
def list_domains(user: CurrentUser = Depends(get_current_user)) -> list[str]:
    return available_domains()


@router.get("/{domain}/experiments", response_model=GenericExperimentListResponse)
def list_domain_experiments(domain: str, ctx: ProjectContext = Depends(get_project_context)) -> GenericExperimentListResponse:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    experiments = [
        GenericExperimentSummary(
            experiment_id=e.experiment_id, name=e.name, control_version=e.control_version,
            treatment_version=e.treatment_version, start_date=e.start_date, end_date=e.end_date,
        )
        for e in adapter.list_experiments()
    ]
    return GenericExperimentListResponse(domain=domain, experiments=experiments)


@router.get("/{domain}/experiments/{experiment_id}/metrics", response_model=GenericMetricTableResponse)
def get_domain_metrics(domain: str, experiment_id: str, ctx: ProjectContext = Depends(get_project_context)) -> GenericMetricTableResponse:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    _experiment_or_404(adapter, experiment_id)
    base_df = adapter.analytics_base_df(experiment_id=experiment_id)
    results = analyze_all_metrics(base_df, adapter.metric_definitions(), metric_value_columns=adapter.metric_value_columns())
    return GenericMetricTableResponse(domain=domain, experiment_id=experiment_id, metrics=[metric_result_to_schema(r) for r in results])


@router.get("/{domain}/experiments/{experiment_id}/guardrails", response_model=GenericGuardrailResponse)
def get_domain_guardrails(domain: str, experiment_id: str, ctx: ProjectContext = Depends(get_project_context)) -> GenericGuardrailResponse:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    _experiment_or_404(adapter, experiment_id)
    base_df = adapter.analytics_base_df(experiment_id=experiment_id)
    definitions = adapter.guardrails()
    report = evaluate_guardrails(base_df, definitions)
    metric_by_name = {gd.name: gd.metric for gd in definitions}
    checks = [
        GenericGuardrailCheckSchema(
            name=c.name, metric=metric_by_name.get(c.name, ""), v1_value=c.v1_value, v2_value=c.v2_value,
            threshold_description=c.threshold_description, breached=c.breached, severity=c.severity,
        )
        for c in report.checks
    ]
    return GenericGuardrailResponse(domain=domain, experiment_id=experiment_id, checks=checks, any_breach=report.any_breach, any_warning_breach=report.any_warning_breach)


@router.get("/{domain}/experiments/{experiment_id}/investigation", response_model=GenericInvestigationResponse)
def get_domain_investigation(
    domain: str,
    experiment_id: str,
    primary_metric: str = Query(..., description="Required: one of this domain's implemented, inferential metrics. No default."),
    ctx: ProjectContext = Depends(get_project_context),
) -> GenericInvestigationResponse:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    _experiment_or_404(adapter, experiment_id)
    _validate_primary_metric(adapter, primary_metric)

    config = investigation_config_from_adapter(adapter)
    base_df = adapter.analytics_base_df(experiment_id=experiment_id)
    agent_actions_df = adapter.agent_actions_df(experiment_id=experiment_id)
    failure_attributions_wide_df = adapter.failure_attributions_wide_df()
    result = run_investigation(base_df, agent_actions_df, failure_attributions_wide_df, config, primary_metric_name=primary_metric)

    scan_by_label = {row.segment.label: row for row in result.scan_rows}
    top_labels = {f.segment_label for f in result.findings}
    explored = [
        ExploredSegmentSummary(
            segment_label=label, p_value=row.result.p_value, bh_significant=row.bh_significant,
            meets_min_effect=row.meets_min_effect, verdict=row.result.verdict,
        )
        for label, row in scan_by_label.items()
        if label not in top_labels
    ]
    metric_by_name = {gd.name: gd.metric for gd in config.guardrails}
    guardrail_schemas = [
        GenericGuardrailCheckSchema(
            name=c.name, metric=metric_by_name.get(c.name, ""), v1_value=c.v1_value, v2_value=c.v2_value,
            threshold_description=c.threshold_description, breached=c.breached, severity=c.severity,
        )
        for c in result.guardrails.checks
    ]

    return GenericInvestigationResponse(
        domain=domain,
        experiment_id=experiment_id,
        primary_metric=result.primary_metric,
        overall=metric_result_to_schema(result.overall),
        guardrails=guardrail_schemas,
        any_guardrail_breach=result.guardrails.any_breach,
        findings=[finding_to_schema(f) for f in result.findings],
        explored_not_significant=explored,
        recommendation=RecommendationSchema(
            verdict=result.recommendation.verdict,
            primary_reason=result.recommendation.primary_reason,
            blocking_guardrails=result.recommendation.blocking_guardrails,
            next_action=result.recommendation.next_action,
            rules_applied=result.recommendation.rules_applied,
        ),
    )


@router.get("/{domain}/mechanisms", response_model=MechanismListResponse)
def get_domain_mechanisms(domain: str, ctx: ProjectContext = Depends(get_project_context)) -> MechanismListResponse:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    mechanisms = [MechanismSchema(name=m.name, source=m.source, description=m.description) for m in adapter.mechanisms()]
    return MechanismListResponse(domain=domain, mechanisms=mechanisms)


@router.get("/{domain}/sessions", response_model=GenericSessionListResponse)
def list_domain_sessions(
    domain: str,
    experiment_id: str | None = None,
    agent_version: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    ctx: ProjectContext = Depends(get_project_context),
) -> GenericSessionListResponse:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    df = adapter.analytics_base_df(experiment_id=experiment_id)
    if agent_version is not None:
        df = df[df["agent_version"] == agent_version]

    total = len(df)
    sort_col = "started_at" if "started_at" in df.columns else "session_id"
    page = df.sort_values(sort_col, ascending=False).iloc[offset : offset + limit]

    outcome_col = "outcome" if "outcome" in df.columns else ("outcome_label" if "outcome_label" in df.columns else None)
    items = [
        GenericSessionSummary(
            session_id=str(row.session_id),
            agent_version=row.agent_version,
            outcome=(getattr(row, outcome_col) if outcome_col else None),
            started_at=getattr(row, "started_at", None),
        )
        for row in page.itertuples()
    ]
    return GenericSessionListResponse(domain=domain, items=items, total=total, limit=limit, offset=offset)


@router.get("/{domain}/sessions/{session_id}", response_model=GenericSessionDetailResponse)
def get_domain_session_detail(domain: str, session_id: str, ctx: ProjectContext = Depends(get_project_context)) -> GenericSessionDetailResponse:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    try:
        ctx_session = adapter.build_session_context(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No session with id '{session_id}' in domain '{domain}'")

    attributions = adapter.list_reviewable_attributions(session_id=session_id)
    reviews_by_mode = get_reviews_for_session(get_engine(), domain, session_id, project_id=ctx.project.project_id)
    failure_attributions = [
        GenericFailureAttributionSchema(
            failure_mode=a.failure_mode, detector_source=a.detector_source, confidence=a.confidence, evidence_text=a.evidence_text,
            review_status=(reviews_by_mode[a.failure_mode].decision if a.failure_mode in reviews_by_mode else "unreviewed"),
            corrected_mechanism=(reviews_by_mode[a.failure_mode].corrected_mechanism if a.failure_mode in reviews_by_mode else None),
            review_note=(reviews_by_mode[a.failure_mode].note if a.failure_mode in reviews_by_mode else None),
        )
        for a in attributions
    ]

    return GenericSessionDetailResponse(
        domain=domain,
        session_id=str(ctx_session.session_id),
        outcome=ctx_session.outcome,
        transcript=[[sender, text] for sender, text in ctx_session.transcript],
        action_sequence=list(ctx_session.action_sequence),
        tool_calls=[GenericToolCallSchema(tool_name=tc.tool_name, success=tc.success, error_type=tc.error_type) for tc in ctx_session.tool_calls],
        failure_attributions=failure_attributions,
    )


@router.post("/{domain}/experiments/{experiment_id}/release-evaluations", response_model=ReleaseEvaluationSchema, status_code=201)
def create_release_evaluation(
    domain: str,
    experiment_id: str,
    primary_metric: str = Query(..., description="Required: one of this domain's implemented, inferential metrics."),
    ctx: ProjectContext = Depends(require_role("analyst")),
) -> ReleaseEvaluationSchema:
    """Stage 5 task 4: evaluate this experiment RIGHT NOW (no scheduling)
    and persist the result — every call appends a new release_evaluations
    row, so calling this repeatedly builds the release history task 3
    asks for. Stage 7 task 3: requires "analyst" role or higher."""
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    _experiment_or_404(adapter, experiment_id)
    _validate_primary_metric(adapter, primary_metric)

    result = evaluate_and_persist_release(get_engine(), domain, experiment_id, adapter, primary_metric, project_id=ctx.project.project_id)
    return ReleaseEvaluationSchema(**result.__dict__)


@router.get("/{domain}/experiments/{experiment_id}/release-status", response_model=ReleaseEvaluationSchema)
def get_release_status(domain: str, experiment_id: str, ctx: ProjectContext = Depends(get_project_context)) -> ReleaseEvaluationSchema:
    result = get_latest_release_status(get_engine(), domain, experiment_id, project_id=ctx.project.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No release evaluation has been run yet for domain='{domain}' experiment_id='{experiment_id}'")
    return ReleaseEvaluationSchema(**result.__dict__)


@router.get("/{domain}/experiments/{experiment_id}/release-history", response_model=ReleaseHistoryResponse)
def get_release_history(
    domain: str, experiment_id: str, limit: int = Query(default=20, le=100), ctx: ProjectContext = Depends(get_project_context)
) -> ReleaseHistoryResponse:
    results = list_release_history(get_engine(), domain, experiment_id, project_id=ctx.project.project_id, limit=limit)
    return ReleaseHistoryResponse(domain=domain, experiment_id=experiment_id, evaluations=[ReleaseEvaluationSchema(**r.__dict__) for r in results])


@router.get("/{domain}/experiments/{experiment_id}/release-evaluations/{evaluation_id}/evidence", response_model=ReleaseEvidenceResponse)
def get_release_evidence(
    domain: str, experiment_id: str, evaluation_id: str, ctx: ProjectContext = Depends(get_project_context)
) -> ReleaseEvidenceResponse:
    """Stage 11 task 3: the evidence layer for one past release decision
    — breached guardrails, significant negative segments, the small
    deterministic set of sessions that illustrate them (task 4), and any
    linked, already-detected failure mechanism (Stage 6). Every field
    here is either already stored on the evaluation row or re-read live
    from the same adapter/project the evaluation itself used — nothing is
    inferred or generated."""
    evaluation = get_release_evaluation_by_id(get_engine(), evaluation_id, project_id=ctx.project.project_id)
    if evaluation is None or evaluation.experiment_id != experiment_id or evaluation.domain != domain:
        raise HTTPException(status_code=404, detail=f"No release evaluation '{evaluation_id}' for domain='{domain}' experiment_id='{experiment_id}'")

    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    evidence = build_release_evidence(adapter, evaluation)
    return ReleaseEvidenceResponse(
        evaluation_id=evidence.evaluation_id,
        domain=evidence.domain,
        experiment_id=evidence.experiment_id,
        status=evidence.status,
        breached_guardrails=evidence.breached_guardrails,
        significant_negative_segments=[
            NegativeSegmentEvidenceSchema(
                segment_label=s.segment_label, dimensions=list(s.dimensions), p_value=s.p_value,
                excess_contribution=s.excess_contribution, dominant_failure_mode=s.dominant_failure_mode,
                representative_session_ids=s.representative_session_ids,
            )
            for s in evidence.significant_negative_segments
        ],
        representative_sessions=[
            SessionEvidenceSchema(
                session_id=s.session_id, segment_label=s.segment_label, outcome=s.outcome,
                transcript_excerpt=[list(t) for t in s.transcript_excerpt], action_sequence=s.action_sequence,
            )
            for s in evidence.representative_sessions
        ],
        linked_failure_mechanisms=[
            LinkedMechanismSchema(
                session_id=m.session_id, failure_mode=m.failure_mode, detector_source=m.detector_source,
                confidence=m.confidence, evidence_text=m.evidence_text,
            )
            for m in evidence.linked_failure_mechanisms
        ],
    )


@router.get("/{domain}/data-quality", response_model=DataQualityReportResponse)
def get_data_quality_report(domain: str, ctx: ProjectContext = Depends(get_project_context)) -> DataQualityReportResponse:
    """Stage 11 tasks 5-7: this project's data-quality report — see
    backend.quality.service for the checks and their deterministic
    thresholds. A project with no ingested data yet is reported healthy
    with a "not_applicable" note, never silently omitted."""
    report = compute_data_quality_report(get_engine(), ctx.project.project_id, domain)
    return DataQualityReportResponse(
        project_id=report.project_id,
        domain=report.domain,
        status=report.status,
        generated_at=report.generated_at,
        checks=[{"name": c.name, "value": c.value, "status": c.status, "detail": c.detail} for c in report.checks],
    )
