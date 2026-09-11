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

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.analytics.cache_utils import (
    data_version_registry,
    investigation_cache,
    investigation_config_fingerprint,
    metric_defs_fingerprint,
    metrics_table_cache,
)
from backend.analytics.experiment_results import analyze_all_metrics, analyze_metric
from backend.app.auth_deps import CurrentUser, ProjectContext, get_current_user, get_project_context, require_role
from backend.app.domain_registry import available_domains, get_adapter, get_engine
from backend.app.routers.experiments import _status_chip
from backend.app.investigation_serialization import finding_to_schema
from backend.audit.service import record_audit_event
from backend.app.schemas.common import metric_result_to_schema
from backend.app.schemas.domain_generic import (
    ConfidenceBucketQualitySchema,
    ConfusionPairSchema,
    DisagreementItemSchema,
    DetectorSourceQualitySchema,
    GenericAIQualitySummaryResponse,
    GenericExperimentListResponse,
    GenericExperimentSummary,
    GenericFailureAttributionSchema,
    GenericFailureMechanismPrevalenceItem,
    GenericFunnelResponse,
    GenericFunnelSeries,
    GenericFunnelStagePoint,
    GenericGuardrailCheckSchema,
    GenericGuardrailResponse,
    GenericInvestigationResponse,
    GenericMetricTableResponse,
    GenericSessionDetailResponse,
    GenericSessionListResponse,
    GenericSessionSummary,
    GenericToolCallSchema,
    GenericToolUseQuality,
    GenericTrajectoryPatternItem,
    HumanReviewQualityReport,
    MechanismListResponse,
    MechanismQualitySchema,
    MechanismSchema,
    DataQualityReportResponse,
    LinkedMechanismSchema,
    NegativeSegmentEvidenceSchema,
    QualityCountsSchema,
    ReleaseEvaluationSchema,
    ReleaseEvidenceResponse,
    ReleaseHistoryResponse,
    SegmentDimensionsResponse,
    SessionEvidenceSchema,
    VersionQualityBucketSchema,
)
from backend.app.schemas.investigation import ExploredSegmentSummary, RecommendationSchema
from backend.app.schemas.project_config import (
    AvailableGuardrailSchema,
    AvailableMetricSchema,
    OnboardingStatusResponse,
    ProjectConfigRequest,
    ProjectConfigSchema,
)
from backend.app.schemas.release_summary import ReleaseSummaryResponse
from backend.core.adapter import DomainAdapter
from backend.core.config import load_metric_config_from_dict
from backend.core.guardrails import evaluate_guardrails
from backend.core.investigation_config import investigation_config_from_adapter
from backend.investigation.pipeline import run_investigation
from backend.investigation.trajectory_attribution import canonicalize_patterns, reconstruct_trajectories
from backend.monitoring.service import list_monitoring_configs
from backend.notifications.service import list_channels as list_notification_channels
from backend.project_config.service import existing_context_keys, get_project_config, upsert_project_config, validate_project_config
from backend.quality.service import compute_data_quality_report
from backend.release.evidence import build_release_evidence
from backend.release.service import evaluate_and_persist_release, get_latest_release_status, get_release_evaluation_by_id, list_release_history
from backend.release.summary import build_release_summary
from backend.review.quality import MIN_REVIEWS_FOR_QUALITY_CLAIM, compute_attribution_quality, compute_disagreement_analysis, compute_quality_by_version
from backend.review.service import count_reviews_by_mechanism, get_reviews_for_session, list_reviews_for_sessions

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


# Stage 17 task 5/6 perf fix: analyze_all_metrics runs a bootstrap CI per
# metric -- ~30 metrics on commerce measured at ~23s total on the demo
# dataset, one of the slowest computations in the main flow (GET
# .../metrics, which Experiment and Investigation both depend on -- and,
# via backend.release.service.evaluate_release, so does POST
# .../release-evaluations and scheduled monitoring). Cached per (domain,
# project, experiment) via backend.analytics.cache_utils.metrics_table_cache
# -- a bounded LRU shared with evaluate_release's own use of the same
# cache (see backend/release/service.py), so whichever of "view the
# metrics table" / "run an investigation" / "evaluate a release" happens
# first warms it for the others, instead of each independently paying for
# the same computation. Keyed additionally on a cheap fingerprint of the
# EFFECTIVE metric definitions (name/implemented/is_inferential per
# metric) so a project that edits its own metrics config
# (backend.project_config) invalidates itself the moment that config
# actually changes, without this module needing to know when that
# happened. ALSO keyed on len(base_df) AND
# data_version_registry.current(project_id) (Stage 18 task 6): unlike
# commerce (static dataset, safe to cache indefinitely -- see
# CommerceAdapter._cached_session_level_base), the support domain's
# ingested_* tables are genuinely live. Row count alone catches new rows
# arriving but misses an in-place UPDATE of an existing row's content
# (backend.ingestion.service.ingest_batch's upsert, or
# backend.connectors.postgres_business.service.run_enrichment layering
# business metrics onto existing sessions, can both do exactly that) --
# the version counter, bumped explicitly at the end of both write paths,
# is the deterministic signal that actually covers that case.
def _cached_analyze_all_metrics(domain: str, project_id: str, experiment_id: str, base_df, metric_defs, metric_value_columns):
    # window_key is always None here (this endpoint never applies a
    # window) -- kept as an explicit slot, in the same position
    # evaluate_release's key uses, purely so an unwindowed call from
    # either path produces the identical key and actually shares the
    # cache entry, instead of two structurally different tuples that
    # happen to mean the same thing.
    key = (
        domain, project_id, experiment_id, metric_defs_fingerprint(metric_defs), None,
        len(base_df), data_version_registry.current(project_id),
    )
    return metrics_table_cache.get_or_compute(key, lambda: analyze_all_metrics(base_df, metric_defs, metric_value_columns=metric_value_columns))


# Stage 17 task 5/6 perf fix: run_investigation's segment scan calls
# analyze_metric ~58 times on commerce (57 registered segments + the
# overall comparison), and EVERY call that clears the sparse-data gate
# runs a 10,000-resample cluster bootstrap CI
# (backend.analytics.stats.bootstrap.cluster_bootstrap_ci) -- that cost is
# what made both GET .../investigation (~21s) and, worse, POST
# .../release-evaluations (~64s, since evaluate_release also separately
# calls analyze_all_metrics -- see backend/release/service.py) among the
# slowest requests in the app, unmoved by the base_df/agent_actions_df
# caches above since those only cut the SQL fetch, not this in-process
# statistical compute. The bootstrap is already fully vectorized and
# deterministic (fixed seed); there is no cheaper way to compute the SAME
# confidence intervals, so rather than touch STATISTICS.md's bootstrap
# procedure this caches the whole InvestigationResult via
# backend.analytics.cache_utils.investigation_cache -- shared with
# evaluate_release the same way the metrics cache above is, same key
# shape (domain/project/experiment/primary_metric, fingerprinted config,
# row counts AND the explicit data-version counter as staleness signals
# -- see the matching comment on _cached_analyze_all_metrics for why row
# counts alone aren't enough). A cache hit returns an identical result
# object.
def _cached_run_investigation(domain, project_id, experiment_id, primary_metric, base_df, agent_actions_df, failure_attributions_wide_df, config):
    # window_key is always None here (this endpoint never applies a
    # window) -- see the matching comment in _cached_analyze_all_metrics.
    key = (
        domain, project_id, experiment_id, primary_metric, investigation_config_fingerprint(config), None,
        len(base_df), len(agent_actions_df), len(failure_attributions_wide_df), data_version_registry.current(project_id),
    )
    return investigation_cache.get_or_compute(
        key, lambda: run_investigation(base_df, agent_actions_df, failure_attributions_wide_df, config, primary_metric_name=primary_metric)
    )


@router.get("", response_model=list[str])
def list_domains(user: CurrentUser = Depends(get_current_user)) -> list[str]:
    return available_domains()


@router.get("/{domain}/experiments", response_model=GenericExperimentListResponse)
def list_domain_experiments(domain: str, ctx: ProjectContext = Depends(get_project_context)) -> GenericExperimentListResponse:
    """Stage 16: also carries each experiment's north-star metric and
    status chip -- the same computation backend.app.routers.experiments.
    list_experiments already performs for the legacy commerce-only route
    (same analyze_metric/evaluate_guardrails/_status_chip, reused not
    reimplemented), generalized to any domain's own configured primary
    metric instead of a hardcoded "conversion_rate". This is what the
    Overview screen's portfolio cards render for a project of any domain."""
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    config = get_project_config(get_engine(), ctx.project.project_id)
    primary_metric = config.primary_metric if config else None
    metric_def = next((m for m in adapter.metric_definitions() if m.name == primary_metric), None) if primary_metric else None

    experiments = []
    for e in adapter.list_experiments():
        n_sessions = n_users = None
        north_star_schema = None
        status_chip: str = "not_yet_investigated"
        if metric_def is not None:
            base_df = adapter.analytics_base_df(experiment_id=e.experiment_id)
            north_star = analyze_metric(base_df, metric_def, metric_value_columns=adapter.metric_value_columns())
            guardrail_report = evaluate_guardrails(base_df, adapter.guardrails())
            n_sessions = north_star.n_sessions_v1 + north_star.n_sessions_v2
            n_users = north_star.n_users_v1 + north_star.n_users_v2
            north_star_schema = metric_result_to_schema(north_star)
            status_chip = _status_chip(north_star, guardrail_report.any_breach, direction=metric_def.direction)
        experiments.append(
            GenericExperimentSummary(
                experiment_id=e.experiment_id, name=e.name, control_version=e.control_version,
                treatment_version=e.treatment_version, start_date=e.start_date, end_date=e.end_date,
                n_sessions=n_sessions, n_users=n_users, north_star_metric=north_star_schema, status_chip=status_chip,
            )
        )
    return GenericExperimentListResponse(domain=domain, experiments=experiments)


@router.get("/{domain}/experiments/{experiment_id}/metrics", response_model=GenericMetricTableResponse)
def get_domain_metrics(domain: str, experiment_id: str, ctx: ProjectContext = Depends(get_project_context)) -> GenericMetricTableResponse:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    _experiment_or_404(adapter, experiment_id)
    base_df = adapter.analytics_base_df(experiment_id=experiment_id)
    results = _cached_analyze_all_metrics(domain, ctx.project.project_id, experiment_id, base_df, adapter.metric_definitions(), adapter.metric_value_columns())
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


# Stage 16: the funnel concept (impression -> click -> cart -> purchase)
# is inherently commerce-shaped, not a generic session-analytics concept.
# These are the funnel-stage columns session_level_base.sql produces for
# commerce; a domain whose analytics_base_df carries none of them (e.g.
# support) is reported as not applicable rather than guessing a funnel
# that doesn't exist for it. This mirrors list_domain_sessions' own
# column-presence check just below (outcome vs outcome_label) -- this
# file stays free of any import from backend.domains.commerce/support,
# it only ever inspects column names already present on the adapter's df.
_FUNNEL_STAGE_COLUMNS = [("impression", "had_impression"), ("click", "had_click"), ("cart", "had_cart"), ("purchase", "had_purchase")]


@router.get("/{domain}/experiments/{experiment_id}/funnel", response_model=GenericFunnelResponse)
def get_domain_funnel(domain: str, experiment_id: str, ctx: ProjectContext = Depends(get_project_context)) -> GenericFunnelResponse:
    """Reuses the exact computation backend.app.routers.experiments.
    get_experiment_funnel already performs for the legacy commerce-only
    route, generalized to be project/domain-scoped via the adapter's own
    analytics_base_df instead of the unscoped get_base_df."""
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    _experiment_or_404(adapter, experiment_id)
    base_df = adapter.analytics_base_df(experiment_id=experiment_id)

    stage_cols = [(label, col) for label, col in _FUNNEL_STAGE_COLUMNS if col in base_df.columns]
    if not stage_cols or "agent_version" not in base_df.columns:
        return GenericFunnelResponse(domain=domain, experiment_id=experiment_id, applicable=False, series=[])

    series = []
    for version, group in base_df.groupby("agent_version"):
        stages = []
        prev_n: int | None = None
        for label, col in stage_cols:
            n = int(group[col].sum())
            stages.append(GenericFunnelStagePoint(stage=label, n_sessions=n, conversion_from_previous=(n / prev_n) if prev_n else None))
            prev_n = n
        series.append(GenericFunnelSeries(agent_version=version, n_sessions=len(group), stages=stages))
    return GenericFunnelResponse(domain=domain, experiment_id=experiment_id, applicable=True, series=series)


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
    result = _cached_run_investigation(
        domain, ctx.project.project_id, experiment_id, primary_metric, base_df, agent_actions_df, failure_attributions_wide_df, config
    )

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


@router.get("/{domain}/segment-dimensions", response_model=SegmentDimensionsResponse)
def get_domain_segment_dimensions(domain: str, ctx: ProjectContext = Depends(get_project_context)) -> SegmentDimensionsResponse:
    """Stage 17 task 3: lets the frontend build a sessions-filter UI (and
    any other segment-dimension picker) from this project's own
    dimensions/values, never a hardcoded commerce list. A project's own
    segment_dimensions override (backend.project_config.overrides) is
    already what adapter.segment_dimensions() returns when one exists."""
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    return SegmentDimensionsResponse(domain=domain, dimensions=adapter.segment_dimensions())


def _human_review_quality_report(engine, domain: str, project_id: str, attributions: list) -> HumanReviewQualityReport:
    """Stage 19 tasks 1/2/3/4: real human-review-based quality for this
    experiment's reviewable attributions -- distinct from, and shown
    alongside, the offline classifier benchmark
    (ClassifierEvaluationResponse.hybrid_evaluation). Every rate here is
    over REVIEWED items only (compute_attribution_quality never counts
    an unreviewed attribution as correct or incorrect)."""
    session_ids = {a.session_id for a in attributions}
    reviews_by_session = list_reviews_for_sessions(engine, domain, session_ids, project_id=project_id)
    reviews_by_key = {(sid, mode): review for sid, by_mode in reviews_by_session.items() for mode, review in by_mode.items()}

    quality = compute_attribution_quality(attributions, reviews_by_key)
    by_version = compute_quality_by_version(attributions, reviews_by_key)
    disagreement = compute_disagreement_analysis(attributions, reviews_by_key)

    def _counts_schema(c) -> QualityCountsSchema:
        return QualityCountsSchema(
            reviewed_count=c.reviewed_count, confirmed_count=c.confirmed_count, rejected_count=c.rejected_count,
            corrected_count=c.corrected_count, confirmation_rate=c.confirmation_rate, correction_rate=c.correction_rate,
            sample_status=c.sample_status,
        )

    return HumanReviewQualityReport(
        overall=_counts_schema(quality.overall),
        by_mechanism=[MechanismQualitySchema(failure_mode=m.failure_mode, detector_source=m.detector_source, counts=_counts_schema(m.counts)) for m in quality.by_mechanism],
        by_detector_source=[DetectorSourceQualitySchema(detector_source=s.detector_source, counts=_counts_schema(s.counts)) for s in quality.by_detector_source],
        by_confidence_bucket=[
            ConfidenceBucketQualitySchema(bucket_label=b.bucket_label, bucket_min=b.bucket_min, bucket_max=b.bucket_max, counts=_counts_schema(b.counts))
            for b in quality.by_confidence_bucket
        ],
        by_version=[
            VersionQualityBucketSchema(
                detector_version=v.detector_version, provider=v.provider, model=v.model, prompt_version=v.prompt_version,
                first_seen=v.first_seen, last_seen=v.last_seen, counts=_counts_schema(v.counts),
            )
            for v in by_version
        ],
        disagreement_items=[
            DisagreementItemSchema(
                session_id=i.session_id, experiment_id=i.experiment_id, original_mechanism=i.original_mechanism,
                corrected_mechanism=i.corrected_mechanism, original_confidence=i.original_confidence, detector_source=i.detector_source,
                detector_version=i.detector_version, provider=i.provider, model=i.model, prompt_version=i.prompt_version,
                reviewed_at=i.reviewed_at,
            )
            for i in disagreement.items
        ],
        confusion_pairs=[
            ConfusionPairSchema(original_mechanism=p.original_mechanism, corrected_mechanism=p.corrected_mechanism, count=p.count)
            for p in disagreement.confusion_pairs
        ],
        min_reviews_threshold=MIN_REVIEWS_FOR_QUALITY_CLAIM,
    )


@router.get("/{domain}/experiments/{experiment_id}/ai-quality", response_model=GenericAIQualitySummaryResponse)
def get_domain_ai_quality(domain: str, experiment_id: str, ctx: ProjectContext = Depends(get_project_context)) -> GenericAIQualitySummaryResponse:
    """Reuses the exact computation backend.app.routers.ai_quality.
    get_ai_quality_summary already performs, generalized via the adapter:
    project-scoped failure attributions from list_reviewable_attributions
    (empty for a domain with no attribution storage, e.g. support -- the
    same "empty is valid" contract as get_domain_mechanisms), the
    adapter's own trajectory_config for outcome/negative-outcome/action
    vocabulary instead of commerce's literals, and column-presence checks
    for tool-use fields whose exact names differ per domain (commerce's
    *_session suffix vs support's bare names) -- nulling out a field
    rather than guessing when a domain's data doesn't carry it."""
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    _experiment_or_404(adapter, experiment_id)
    base_df = adapter.analytics_base_df(experiment_id=experiment_id)
    v1_mask = base_df["agent_version"] == "v1"
    v2_mask = base_df["agent_version"] == "v2"
    n_v1, n_v2 = int(v1_mask.sum()), int(v2_mask.sum())

    attributions = adapter.list_reviewable_attributions(experiment_id=experiment_id)
    counts: dict[str, dict[str, int]] = {}
    sources: dict[str, str] = {}
    for a in attributions:
        by_version = counts.setdefault(a.failure_mode, {})
        by_version[a.agent_version] = by_version.get(a.agent_version, 0) + 1
        sources[a.failure_mode] = a.detector_source
    review_counts = count_reviews_by_mechanism(get_engine(), domain, set(base_df["session_id"].astype(str)), project_id=ctx.project.project_id)
    prevalence = [
        GenericFailureMechanismPrevalenceItem(
            failure_mode=m.name,
            detector_source=sources.get(m.name, m.source),
            count_v1=counts.get(m.name, {}).get("v1", 0),
            count_v2=counts.get(m.name, {}).get("v2", 0),
            rate_v1=(counts.get(m.name, {}).get("v1", 0) / n_v1) if n_v1 else 0.0,
            rate_v2=(counts.get(m.name, {}).get("v2", 0) / n_v2) if n_v2 else 0.0,
            reviewed_count=review_counts.get(m.name, {}).get("reviewed", 0),
            confirmed_count=review_counts.get(m.name, {}).get("confirmed", 0),
            rejected_count=review_counts.get(m.name, {}).get("rejected", 0),
        )
        for m in adapter.mechanisms().mechanisms
    ]

    def _mean(col_candidates: list[str], mask) -> float | None:
        for col in col_candidates:
            if col in base_df.columns:
                values = base_df.loc[mask, col].dropna()
                return float(values.mean()) if len(values) else None
        return None

    tool_use = GenericToolUseQuality(
        tool_calls_per_session_v1=_mean(["n_tool_calls"], v1_mask),
        tool_calls_per_session_v2=_mean(["n_tool_calls"], v2_mask),
        tool_success_rate_v1=_mean(["tool_success_rate_session", "tool_success_rate"], v1_mask),
        tool_success_rate_v2=_mean(["tool_success_rate_session", "tool_success_rate"], v2_mask),
        tool_error_rate_v1=_mean(["tool_error_rate_session"], v1_mask),
        tool_error_rate_v2=_mean(["tool_error_rate_session"], v2_mask),
    )

    traj_config = adapter.trajectory_config()
    trajectories = reconstruct_trajectories(adapter.agent_actions_df(experiment_id=experiment_id))
    merged = base_df.merge(trajectories, on="session_id", how="left").dropna(subset=["action_sequence"])
    traj_items: list[GenericTrajectoryPatternItem] = []
    if not merged.empty and traj_config.outcome_column in merged.columns:
        canon = canonicalize_patterns(
            merged, clarify_action=traj_config.clarify_action, repeat_action=traj_config.repeat_action,
            terminal_negative_action=traj_config.terminal_negative_action,
        )
        for pattern, group in canon.groupby("pattern"):
            v1 = group[group.agent_version == "v1"]
            v2 = group[group.agent_version == "v2"]
            if len(v1) + len(v2) < 5:
                continue
            traj_items.append(
                GenericTrajectoryPatternItem(
                    pattern=pattern, n_sessions_v1=len(v1), n_sessions_v2=len(v2),
                    negative_outcome_rate_v1=float((v1[traj_config.outcome_column] == traj_config.negative_outcome_value).mean()) if len(v1) else 0.0,
                    negative_outcome_rate_v2=float((v2[traj_config.outcome_column] == traj_config.negative_outcome_value).mean()) if len(v2) else 0.0,
                )
            )
        traj_items.sort(key=lambda t: t.n_sessions_v1 + t.n_sessions_v2, reverse=True)

    human_review_quality = _human_review_quality_report(get_engine(), domain, ctx.project.project_id, attributions)

    return GenericAIQualitySummaryResponse(
        domain=domain, experiment_id=experiment_id,
        failure_mechanism_prevalence=prevalence, tool_use_quality=tool_use, trajectory_patterns=traj_items,
        human_review_quality=human_review_quality,
    )


def _session_review_status(mechanisms: list[str], reviews_for_session: dict[str, object]) -> str:
    """One aggregate status per session for a filter/column that has to
    show one value per row, even though review is stored per (session,
    failure_mode). "unreviewed" when nothing detected has been reviewed
    at all (including sessions with nothing detected to review); "mixed"
    when reviewed mechanisms disagree."""
    decisions = {reviews_for_session[m].decision for m in mechanisms if m in reviews_for_session}  # type: ignore[attr-defined]
    if not decisions:
        return "unreviewed"
    if decisions == {"confirmed"}:
        return "confirmed"
    if decisions == {"rejected"}:
        return "rejected"
    return "mixed"


@router.get("/{domain}/sessions", response_model=GenericSessionListResponse)
def list_domain_sessions(
    domain: str,
    request: Request,
    experiment_id: str | None = None,
    agent_version: str | None = None,
    outcome: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    detected_mechanism: str | None = Query(default=None, description="One of this domain's registered mechanism names; empty for a domain with no attribution storage."),
    review_status: str | None = Query(default=None, description="unreviewed | confirmed | rejected | mixed"),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    ctx: ProjectContext = Depends(get_project_context),
) -> GenericSessionListResponse:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    df = adapter.analytics_base_df(experiment_id=experiment_id)
    if agent_version is not None:
        df = df[df["agent_version"] == agent_version]

    outcome_col = "outcome" if "outcome" in df.columns else ("outcome_label" if "outcome_label" in df.columns else None)
    if outcome is not None and outcome_col is not None:
        df = df[df[outcome_col] == outcome]

    if "started_at" in df.columns:
        if started_after is not None:
            df = df[df["started_at"] >= started_after]
        if started_before is not None:
            df = df[df["started_at"] <= started_before]

    # Stage 16: filter by this domain's own registered pre-treatment
    # segment dimensions (backend.core.adapter.DomainAdapter.
    # segment_dimensions) -- the exact same dimension vocabulary
    # Investigation findings already use, so a "View sessions" link built
    # from a Finding's segment filters correctly for any domain, not just
    # commerce's hardcoded columns. Any other query param is ignored here
    # (project_id/experiment_id/agent_version/limit/offset are handled
    # above, via their own typed parameters).
    for key in adapter.segment_dimensions():
        value = request.query_params.get(key)
        if value is not None and key in df.columns:
            df = df[df[key].astype(str) == value]

    # Stage 17 task 3: detected-mechanism and review-status filters, and
    # the per-row detected_mechanisms/review_status fields, all built
    # from adapter.list_reviewable_attributions() -- empty for a domain
    # with no attribution storage (support), same "empty is valid"
    # contract as get_domain_mechanisms.
    mechanisms_by_session: dict[str, list[str]] = {}
    for a in adapter.list_reviewable_attributions(experiment_id=experiment_id):
        mechanisms_by_session.setdefault(a.session_id, []).append(a.failure_mode)
    reviews_by_session = list_reviews_for_sessions(get_engine(), domain, set(mechanisms_by_session.keys()), project_id=ctx.project.project_id)

    if detected_mechanism is not None:
        matching_ids = {sid for sid, modes in mechanisms_by_session.items() if detected_mechanism in modes}
        df = df[df["session_id"].astype(str).isin(matching_ids)]
    if review_status is not None:
        matching_ids = {
            sid
            for sid in df["session_id"].astype(str)
            if _session_review_status(mechanisms_by_session.get(sid, []), reviews_by_session.get(sid, {})) == review_status
        }
        df = df[df["session_id"].astype(str).isin(matching_ids)]

    total = len(df)
    sort_col = "started_at" if "started_at" in df.columns else "session_id"
    page = df.sort_values(sort_col, ascending=False).iloc[offset : offset + limit]

    items = [
        GenericSessionSummary(
            session_id=str(row.session_id),
            agent_version=row.agent_version,
            outcome=(getattr(row, outcome_col) if outcome_col else None),
            started_at=getattr(row, "started_at", None),
            detected_mechanisms=mechanisms_by_session.get(str(row.session_id), []),
            review_status=_session_review_status(mechanisms_by_session.get(str(row.session_id), []), reviews_by_session.get(str(row.session_id), {})),
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
            detector_version=a.detector_version, provider=a.provider, model=a.model, prompt_version=a.prompt_version,
            reviewer=(reviews_by_mode[a.failure_mode].reviewer if a.failure_mode in reviews_by_mode else None),
            reviewed_at=(reviews_by_mode[a.failure_mode].updated_at if a.failure_mode in reviews_by_mode else None),
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
    primary_metric: str | None = Query(default=None, description="One of this domain's implemented, inferential metrics. Optional if this project has a persisted default (Stage 12 task 4)."),
    ctx: ProjectContext = Depends(require_role("analyst")),
) -> ReleaseEvaluationSchema:
    """Stage 5 task 4: evaluate this experiment RIGHT NOW (no scheduling)
    and persist the result — every call appends a new release_evaluations
    row, so calling this repeatedly builds the release history task 3
    asks for. Stage 7 task 3: requires "analyst" role or higher.

    Stage 12 task 4: `primary_metric` falls back to this project's
    persisted config default when omitted, so an onboarded project's
    callers don't have to keep naming it — a project with neither an
    explicit query param nor a persisted default still gets a clear 422."""
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    _experiment_or_404(adapter, experiment_id)

    if primary_metric is None:
        config = get_project_config(get_engine(), ctx.project.project_id)
        primary_metric = config.primary_metric if config else None
        if primary_metric is None:
            raise HTTPException(status_code=422, detail="primary_metric is required (no persisted default configured for this project — see PUT .../config)")
    _validate_primary_metric(adapter, primary_metric)

    result = evaluate_and_persist_release(get_engine(), domain, experiment_id, adapter, primary_metric, project_id=ctx.project.project_id)
    record_audit_event(
        get_engine(), action="release_evaluation.trigger", actor_user_id=ctx.user.user_id, actor_email=ctx.user.email,
        org_id=ctx.project.org_id, project_id=ctx.project.project_id, target=experiment_id,
        metadata={"domain": domain, "primary_metric": primary_metric, "status": result.status},
    )
    return ReleaseEvaluationSchema(**result.__dict__)


@router.get("/{domain}/experiments/{experiment_id}/release-status", response_model=ReleaseEvaluationSchema)
def get_release_status(domain: str, experiment_id: str, ctx: ProjectContext = Depends(get_project_context)) -> ReleaseEvaluationSchema:
    result = get_latest_release_status(get_engine(), domain, experiment_id, project_id=ctx.project.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No release evaluation has been run yet for domain='{domain}' experiment_id='{experiment_id}'")
    return ReleaseEvaluationSchema(**result.__dict__)


@router.get("/{domain}/experiments/{experiment_id}/release-history", response_model=ReleaseHistoryResponse)
def get_release_history(
    domain: str,
    experiment_id: str,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: ProjectContext = Depends(get_project_context),
) -> ReleaseHistoryResponse:
    results, total = list_release_history(get_engine(), domain, experiment_id, project_id=ctx.project.project_id, limit=limit, offset=offset)
    return ReleaseHistoryResponse(
        domain=domain, experiment_id=experiment_id, evaluations=[ReleaseEvaluationSchema(**r.__dict__) for r in results],
        total=total, limit=limit, offset=offset,
    )


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


def _available_metrics(adapter: DomainAdapter) -> list[AvailableMetricSchema]:
    # Stage 17 task 10: previously defaulted an unset label to the raw
    # metric name (`m.label or m.name`) -- MetricDefinition.label's own
    # docstring says "" means "use name", but filling that in HERE meant
    # every consumer always received a non-empty, non-humanized string,
    # silently defeating their own `label || humanizeMetricName(name)`
    # fallback (Investigation.tsx already had exactly that fallback
    # written, and it never fired because of this). Sending the field
    # through as-is lets each consumer decide how to render "no custom
    # label set" -- which for a human-facing UI is humanization, not the
    # raw snake_case name.
    value_columns = adapter.metric_value_columns()
    return [
        AvailableMetricSchema(
            name=m.name, label=m.label, metric_type=m.metric_type, direction=m.direction,
            semantic_class=m.semantic_class, is_inferential=m.is_inferential, is_descriptive=m.is_descriptive,
            value_column=value_columns[m.name][0] if m.name in value_columns else None,
        )
        for m in adapter.metric_definitions()
        if m.implemented
    ]


def _available_guardrails(adapter: DomainAdapter) -> list[AvailableGuardrailSchema]:
    return [
        AvailableGuardrailSchema(
            name=g.name, metric=g.metric, column=g.column, aggregation=g.aggregation, kind=g.kind,
            direction=g.direction, threshold=g.threshold, severity=g.severity, enabled=g.enabled,
        )
        for g in adapter.guardrails()
    ]


def _config_schema(project_id: str, config, adapter: DomainAdapter, engine, domain: str) -> ProjectConfigSchema:
    available_metrics = _available_metrics(adapter)
    available_guardrails = _available_guardrails(adapter)
    available_context_fields = sorted(existing_context_keys(engine, project_id, domain))
    if config is None:
        return ProjectConfigSchema(
            project_id=project_id, primary_metric=None, metrics=None, guardrails=None, segment_dimensions=None,
            economics=None, monitoring_cadence_seconds=None, enabled_notification_rules=[], created_at=None, updated_at=None,
            available_metrics=available_metrics, available_guardrails=available_guardrails,
            available_context_fields=available_context_fields,
        )
    return ProjectConfigSchema(
        **config.__dict__, available_metrics=available_metrics, available_guardrails=available_guardrails,
        available_context_fields=available_context_fields,
    )


@router.get("/{domain}/config", response_model=ProjectConfigSchema)
def get_config(domain: str, ctx: ProjectContext = Depends(get_project_context)) -> ProjectConfigSchema:
    """Stage 12 task 4: this project's persisted configuration. A project
    that has never saved one gets an all-null shell back, not a 404 —
    the domain's static defaults are already in effect either way.

    Stage 15 tasks 3-5: also returns the domain's currently-available
    metrics/guardrails/context fields, so the onboarding UI can offer
    dropdowns and checklists instead of asking a PM to write JSON."""
    engine = get_engine()
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    config = get_project_config(engine, ctx.project.project_id)
    return _config_schema(ctx.project.project_id, config, adapter, engine, domain)


@router.put("/{domain}/config", response_model=ProjectConfigSchema)
def put_config(domain: str, request: ProjectConfigRequest, ctx: ProjectContext = Depends(require_role("analyst"))) -> ProjectConfigSchema:
    """Stage 12 tasks 4-5: full-replace upsert. Any field left out (None)
    means "no override" — the domain's static default applies, same as
    before this project ever configured anything (task 7). Returns 422
    with the actionable validation issue list on any problem; nothing is
    saved when validation fails."""
    engine = get_engine()
    adapter = get_adapter(domain, project_id=ctx.project.project_id)

    if request.metrics is not None:
        try:
            defs, _ = load_metric_config_from_dict(request.metrics)
            effective_metric_names = {d.name for d in defs}
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=json.dumps([{"field": "metrics", "message": f"invalid metrics config: {exc}"}])) from exc
    else:
        effective_metric_names = {m.name for m in adapter.metric_definitions()}

    issues = validate_project_config(
        primary_metric=request.primary_metric,
        metrics_json=request.metrics,
        guardrails_json=request.guardrails,
        segment_dimensions_json=request.segment_dimensions,
        economics_json=request.economics,
        enabled_notification_rules=request.enabled_notification_rules,
        effective_metric_names=effective_metric_names,
        known_context_keys=existing_context_keys(engine, ctx.project.project_id, domain),
    )
    if issues:
        raise HTTPException(status_code=422, detail=json.dumps([{"field": i.field, "message": i.message} for i in issues]))

    result = upsert_project_config(
        engine, ctx.project.project_id, primary_metric=request.primary_metric, metrics_json=request.metrics,
        guardrails_json=request.guardrails, segment_dimensions_json=request.segment_dimensions, economics_json=request.economics,
        monitoring_cadence_seconds=request.monitoring_cadence_seconds, enabled_notification_rules=request.enabled_notification_rules,
    )
    # Stage 18 task 3: record WHICH top-level sections were touched, never
    # the sections' own content — a metrics/guardrails/economics config
    # isn't secret, but keeping this to field names (not values) means a
    # future field added to any of them is safe here by default rather
    # than needing this call site remembered and updated.
    changed_fields = [
        f for f, v in [
            ("primary_metric", request.primary_metric), ("metrics", request.metrics), ("guardrails", request.guardrails),
            ("segment_dimensions", request.segment_dimensions), ("economics", request.economics),
            ("monitoring_cadence_seconds", request.monitoring_cadence_seconds),
            ("enabled_notification_rules", request.enabled_notification_rules),
        ] if v is not None
    ]
    record_audit_event(
        engine, action="project_config.update", actor_user_id=ctx.user.user_id, actor_email=ctx.user.email,
        org_id=ctx.project.org_id, project_id=ctx.project.project_id, target=domain, metadata={"changed_fields": changed_fields},
    )
    return _config_schema(ctx.project.project_id, result, adapter, engine, domain)


@router.get("/{domain}/onboarding-status", response_model=OnboardingStatusResponse)
def get_onboarding_status(domain: str, ctx: ProjectContext = Depends(get_project_context)) -> OnboardingStatusResponse:
    """Stage 12 task 6: is this project ready for analysis? Every field
    here is a direct read of already-existing state — no new checks
    invented beyond what backend.quality/backend.monitoring/backend.
    notifications already compute and store."""
    engine = get_engine()
    project_id = ctx.project.project_id
    adapter = get_adapter(domain, project_id=project_id)

    has_experiments = len(adapter.list_experiments()) > 0
    config = get_project_config(engine, project_id)
    # There is no static "default primary metric" concept for commerce/
    # support (a caller always names one per release-evaluation call) --
    # this is honestly reported as "not configured" until a project
    # explicitly sets one, even though those domains work fine without it.
    primary_metric_configured = bool(config and config.primary_metric)
    guardrails_configured = len(adapter.guardrails()) > 0
    quality = compute_data_quality_report(engine, project_id, domain)
    monitoring_configs = list_monitoring_configs(engine, project_id)
    channels = list_notification_channels(engine, project_id, enabled_only=True)

    return OnboardingStatusResponse(
        project_id=project_id,
        domain=domain,
        ingestion_connected=True,  # an authenticated call against a real project proves the ingestion API is reachable
        data_received=has_experiments,
        primary_metric_configured=primary_metric_configured,
        guardrails_configured=guardrails_configured,
        data_quality_status=quality.status,
        monitoring_enabled=any(c.enabled for c in monitoring_configs),
        notifications_configured=bool(channels) and bool(config and config.enabled_notification_rules),
    )


@router.get("/{domain}/experiments/{experiment_id}/release-summary", response_model=ReleaseSummaryResponse)
def get_release_summary(domain: str, experiment_id: str, ctx: ProjectContext = Depends(get_project_context)) -> ReleaseSummaryResponse:
    """Stage 14 task 5: one endpoint a UI needs for a complete decision
    screen — decision summary, deterministic explanation, evidence
    hierarchy, per-finding explanations, session-level evidence detail,
    economics, data quality, and monitoring window provenance, all for
    the LATEST release evaluation of this experiment. Nothing here is
    computed fresh; backend.release.summary.build_release_summary reads
    only what's already persisted/computed (task 2: no unsupported
    explanations)."""
    engine = get_engine()
    evaluation = get_latest_release_status(engine, domain, experiment_id, project_id=ctx.project.project_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail=f"No release evaluation has been run yet for domain='{domain}' experiment_id='{experiment_id}'")

    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    summary = build_release_summary(engine, adapter, evaluation)
    return ReleaseSummaryResponse(
        decision=summary.decision.__dict__,
        explanation_text=summary.explanation_text,
        evidence_hierarchy=[e.__dict__ for e in summary.evidence_hierarchy],
        findings=[{**f.__dict__, "dimensions": list(f.dimensions)} for f in summary.findings],
        representative_sessions=[
            {**s.__dict__, "transcript_excerpt": [list(t) for t in s.transcript_excerpt]} for s in summary.representative_sessions
        ],
        economics=summary.economics,
        data_quality_status=summary.data_quality_status,
        monitoring_window=summary.monitoring_window.__dict__,
    )
