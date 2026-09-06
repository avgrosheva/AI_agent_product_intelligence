"""Investigation-by-lens endpoint (Stage 3 review requirement #1).

`lens` has no default and is a required query parameter: the caller must
name exactly one pre-registered analytical lens. This router never runs
more than one lens per call and never merges or compares findings across
lenses — each call is one bounded hypothesis family with its own BH
correction (backend.investigation.pipeline.run_investigation), exactly as
approved. There is deliberately no "just tell me the best finding"
endpoint.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Query

from backend.app.dependencies import get_agent_actions_df, get_base_df, get_experiment_or_404, get_failure_labels_df
from backend.app.routers.experiments import _to_schema
from backend.app.schemas.experiments import GuardrailCheckSchema
from backend.app.schemas.investigation import (
    LENS_METADATA,
    ExploredSegmentSummary,
    FailureAttributionSchema,
    FailureModeShare,
    FindingSchema,
    InvestigationLens,
    InvestigationResponse,
    RecommendationSchema,
    SegmentFilter,
    TrajectoryAssociationSchema,
)
from backend.investigation.pipeline import run_investigation

router = APIRouter(tags=["investigation"])


def _finding_to_schema(finding) -> FindingSchema:
    fa = finding.failure_attribution
    return FindingSchema(
        segment_label=finding.segment_label,
        segment_filter=SegmentFilter(dimensions=dict(zip(finding.dimensions, _values_from_label(finding.segment_label)))),
        n_users_v1=finding.n_users_v1,
        n_users_v2=finding.n_users_v2,
        cluster_mean_v1=finding.cluster_mean_v1,
        cluster_mean_v2=finding.cluster_mean_v2,
        p_value=finding.p_value,
        effect_size_value=finding.effect_size_value,
        excess_contribution=finding.excess_contribution,
        dominant_failure_mode=finding.dominant_failure_mode,
        failure_attribution=FailureAttributionSchema(
            n_v1=fa.n_v1, n_v2=fa.n_v2,
            abandonment_rate_v1=fa.abandonment_rate_v1, abandonment_rate_v2=fa.abandonment_rate_v2,
            total_excess_abandonment=fa.total_excess_abandonment, reportable=fa.reportable,
            per_mode=[
                FailureModeShare(
                    failure_mode=m.failure_mode, excess_count=m.excess_count,
                    share_of_excess_abandonment=m.share_of_excess_abandonment,
                    raw_share_of_v2_failures=m.raw_share_of_v2_failures,
                )
                for m in fa.per_mode
            ],
        ),
        trajectory_associations=[
            TrajectoryAssociationSchema(
                pattern=a.pattern, n_sessions=a.n_sessions, pattern_outcome_rate=a.pattern_outcome_rate,
                baseline_outcome_rate=a.baseline_outcome_rate, test_name=a.test_name, p_value=a.p_value,
                bh_significant=a.bh_significant,
            )
            for a in finding.trajectory_associations
        ],
    )


def _values_from_label(segment_label: str) -> list[str]:
    """'constraint_count_bucket=3+ & platform=android' -> ['3+', 'android']."""
    parts = segment_label.split(" & ")
    return [p.split("=", 1)[1] for p in parts]


@lru_cache(maxsize=32)
def _run_investigation_cached(experiment_id: str, lens: InvestigationLens):
    """Cached for the process lifetime, keyed on (experiment_id, lens)
    (Stage 5 SS13: this call was the dominant cost of a 24-27s
    /investigation response at demo scale, and it is deterministic given a
    static dataset and a fixed bootstrap seed — Stage 5 SS11 confirmed
    byte-identical output across repeated runs on the same data)."""
    base_df = get_base_df(experiment_id=experiment_id)
    actions_df = get_agent_actions_df()
    labels_df = get_failure_labels_df()
    lens_meta = LENS_METADATA[lens]
    return run_investigation(base_df, actions_df, labels_df, primary_metric_name=lens_meta["metric_name"])


@router.get("/experiments/{experiment_id}/investigation", response_model=InvestigationResponse)
def get_investigation(
    experiment_id: str,
    lens: InvestigationLens = Query(..., description="Required: exactly one pre-registered analytical lens. No default — the caller must choose."),
) -> InvestigationResponse:
    get_experiment_or_404(experiment_id)
    lens_meta = LENS_METADATA[lens]
    result = _run_investigation_cached(experiment_id, lens)

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

    guardrail_schemas = [
        GuardrailCheckSchema(name=c.name, v1_value=c.v1_value, v2_value=c.v2_value, threshold_description=c.threshold_description, breached=c.breached)
        for c in result.guardrails.checks
    ]

    return InvestigationResponse(
        experiment_id=experiment_id,
        lens=lens,
        lens_role=lens_meta["role"],
        lens_description=lens_meta["description"],
        primary_metric=result.primary_metric,
        overall=_to_schema(result.overall),
        guardrails=guardrail_schemas,
        any_guardrail_breach=result.guardrails.any_breach,
        findings=[_finding_to_schema(f) for f in result.findings],
        explored_not_significant=explored,
        recommendation=RecommendationSchema(
            verdict=result.recommendation.verdict,
            primary_reason=result.recommendation.primary_reason,
            blocking_guardrails=result.recommendation.blocking_guardrails,
            next_action=result.recommendation.next_action,
            rules_applied=result.recommendation.rules_applied,
        ),
    )
