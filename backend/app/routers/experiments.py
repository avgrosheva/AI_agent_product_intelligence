"""Experiment metadata, metric comparison, funnel, and guardrails.

Thin by design: every number comes from backend.analytics (Stage 2) —
this router only loads data, calls the existing functions, and maps their
already-typed dataclasses onto Pydantic schemas.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import text

from backend.analytics import metric_registry
from backend.analytics.experiment_results import MetricResult, analyze_metric
from backend.app.dependencies import get_base_df, get_engine, get_experiment_or_404
from backend.app.schemas.common import MetricResultSchema, SemanticClass
from backend.app.schemas.experiments import (
    ExperimentDetail,
    ExperimentListResponse,
    ExperimentSummary,
    FunnelResponse,
    FunnelStep,
    GuardrailCheckSchema,
    GuardrailResponse,
    MetricTableResponse,
)
from backend.investigation.recommend import check_guardrails

router = APIRouter(tags=["experiments"])


def _to_schema(result: MetricResult) -> MetricResultSchema:
    return MetricResultSchema(
        metric_name=result.metric_name,
        segment=result.segment,
        semantic_class=result.semantic_class,
        is_inferential=result.p_value is not None or result.verdict != "insufficient_evidence",
        n_sessions_v1=result.n_sessions_v1,
        n_sessions_v2=result.n_sessions_v2,
        session_value_v1=result.session_value_v1,
        session_value_v2=result.session_value_v2,
        n_users_v1=result.n_users_v1,
        n_users_v2=result.n_users_v2,
        cluster_mean_v1=result.cluster_mean_v1,
        cluster_mean_v2=result.cluster_mean_v2,
        event_count_v1=result.event_count_v1,
        event_count_v2=result.event_count_v2,
        non_event_count_v1=result.non_event_count_v1,
        non_event_count_v2=result.non_event_count_v2,
        test_name=result.test_name,
        p_value=result.p_value,
        effect_size_name=result.effect_size_name,
        effect_size_value=result.effect_size_value,
        ci_low=result.ci_low,
        ci_high=result.ci_high,
        ci_stat=result.ci_stat,
        verdict=result.verdict,
        notes=result.notes,
    )


@router.get("/experiments", response_model=ExperimentListResponse)
def list_experiments() -> ExperimentListResponse:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT experiment_id::text AS experiment_id, name, control_version, treatment_version, "
                "start_date, end_date, status::text AS status FROM experiments ORDER BY start_date"
            )
        ).mappings().all()

    summaries = []
    for row in rows:
        scoped = get_base_df(experiment_id=row["experiment_id"])
        north_star = analyze_metric(scoped, metric_registry.get("conversion_rate"))
        guardrails = check_guardrails(scoped)
        chip = _status_chip(north_star, guardrails.any_breach)
        summaries.append(
            ExperimentSummary(
                experiment_id=row["experiment_id"],
                name=row["name"],
                control_version=row["control_version"],
                treatment_version=row["treatment_version"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                status=row["status"],
                n_sessions=north_star.n_sessions_v1 + north_star.n_sessions_v2,
                n_users=north_star.n_users_v1 + north_star.n_users_v2,
                north_star_metric=_to_schema(north_star),
                status_chip=chip,
            )
        )
    return ExperimentListResponse(experiments=summaries)


def _status_chip(north_star: MetricResult, any_guardrail_breach: bool) -> Literal["ambiguous_investigate", "no_regression_detected", "not_yet_investigated"]:
    north_star_down = north_star.p_value is not None and north_star.p_value < 0.05 and (north_star.cluster_mean_v2 or 0) < (north_star.cluster_mean_v1 or 0)
    north_star_up_significant = north_star.p_value is not None and north_star.p_value < 0.05 and (north_star.cluster_mean_v2 or 0) > (north_star.cluster_mean_v1 or 0)
    if north_star_down or (any_guardrail_breach and not north_star_up_significant):
        return "ambiguous_investigate"
    return "no_regression_detected"


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetail)
def get_experiment(experiment_id: str) -> ExperimentDetail:
    exp = get_experiment_or_404(experiment_id)
    base_df = get_base_df(experiment_id=experiment_id)
    v1 = base_df[base_df.agent_version == "v1"]
    v2 = base_df[base_df.agent_version == "v2"]
    return ExperimentDetail(
        experiment_id=exp["experiment_id"],
        name=exp["name"],
        control_version=exp["control_version"],
        treatment_version=exp["treatment_version"],
        start_date=exp["start_date"],
        end_date=exp["end_date"],
        status=exp["status"],
        traffic_split=exp["traffic_split"],
        n_sessions_v1=len(v1),
        n_sessions_v2=len(v2),
        n_users_v1=v1["user_id"].nunique(),
        n_users_v2=v2["user_id"].nunique(),
    )


@lru_cache(maxsize=8)
def _get_full_metric_table_cached(experiment_id: str):
    """Full metric table for one experiment, cached for the process
    lifetime (Stage 5 SS13: this computation was the dominant cost of a
    27s /metrics response at demo scale, and it is deterministic given a
    static dataset — same rationale as dependencies._get_full_base_df_cached).
    Always computed over the full registry so a semantic_class filter is a
    cheap post-filter on an already-cached result, not a second cache key
    per filter value."""
    from backend.analytics.experiment_results import analyze_all_metrics

    base_df = get_base_df(experiment_id=experiment_id)
    return analyze_all_metrics(base_df, metric_registry.METRIC_REGISTRY)


@router.get("/experiments/{experiment_id}/metrics", response_model=MetricTableResponse)
def get_experiment_metrics(
    experiment_id: str,
    semantic_class: SemanticClass | None = Query(default=None, description="Filter to one semantic class, e.g. economic_outcome"),
) -> MetricTableResponse:
    get_experiment_or_404(experiment_id)
    results = _get_full_metric_table_cached(experiment_id)
    if semantic_class is not None:
        results = [r for r in results if r.semantic_class == semantic_class]
    return MetricTableResponse(experiment_id=experiment_id, metrics=[_to_schema(r) for r in results])


@router.get("/experiments/{experiment_id}/funnel", response_model=FunnelResponse)
def get_experiment_funnel(experiment_id: str) -> FunnelResponse:
    """Computed from the already experiment-scoped session_level_base
    frame (its had_impression/had_click/had_cart/had_purchase columns are
    exactly 02_funnel_by_version.sql's logic) rather than re-running that
    unscoped .sql file directly — that file spans every experiment in the
    database, which the dev dataset's single experiment made easy to get
    away with (see get_base_df's docstring for the same issue elsewhere)."""
    get_experiment_or_404(experiment_id)
    base_df = get_base_df(experiment_id=experiment_id)

    steps = []
    for version, group in base_df.groupby("agent_version"):
        n_impression = int(group["had_impression"].sum())
        n_click = int(group["had_click"].sum())
        n_cart = int(group["had_cart"].sum())
        n_purchase = int(group["had_purchase"].sum())
        steps.append(
            FunnelStep(
                agent_version=version,
                n_sessions=len(group),
                n_impression=n_impression,
                n_click=n_click,
                n_cart=n_cart,
                n_purchase=n_purchase,
                impression_to_click_rate=(n_click / n_impression) if n_impression else None,
                click_to_cart_rate=(n_cart / n_click) if n_click else None,
                cart_to_purchase_rate=(n_purchase / n_cart) if n_cart else None,
            )
        )
    return FunnelResponse(experiment_id=experiment_id, funnel=steps)


@router.get("/experiments/{experiment_id}/guardrails", response_model=GuardrailResponse)
def get_experiment_guardrails(experiment_id: str) -> GuardrailResponse:
    get_experiment_or_404(experiment_id)
    base_df = get_base_df(experiment_id=experiment_id)
    report = check_guardrails(base_df)
    checks = [
        GuardrailCheckSchema(
            name=c.name, v1_value=c.v1_value, v2_value=c.v2_value,
            threshold_description=c.threshold_description, breached=c.breached,
        )
        for c in report.checks
    ]
    return GuardrailResponse(experiment_id=experiment_id, checks=checks, any_breach=report.any_breach)
