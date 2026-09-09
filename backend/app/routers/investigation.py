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

from fastapi import APIRouter, Depends, Query

from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.dependencies import get_agent_actions_df, get_base_df, get_experiment_or_404, get_failure_attributions_wide_df
from backend.app.investigation_serialization import finding_to_schema
from backend.app.routers.experiments import _to_schema
from backend.app.schemas.experiments import GuardrailCheckSchema
from backend.app.schemas.investigation import (
    LENS_METADATA,
    ExploredSegmentSummary,
    InvestigationLens,
    InvestigationResponse,
    RecommendationSchema,
)
from backend.domains.commerce.investigation_config import commerce_investigation_config
from backend.investigation.pipeline import run_investigation

router = APIRouter(tags=["investigation"])


@lru_cache(maxsize=32)
def _run_investigation_cached(experiment_id: str, lens: InvestigationLens):
    """Cached for the process lifetime, keyed on (experiment_id, lens)
    (Stage 5 SS13: this call was the dominant cost of a 24-27s
    /investigation response at demo scale, and it is deterministic given a
    static dataset and a fixed bootstrap seed — Stage 5 SS11 confirmed
    byte-identical output across repeated runs on the same data)."""
    base_df = get_base_df(experiment_id=experiment_id)
    actions_df = get_agent_actions_df()
    attributions_wide_df = get_failure_attributions_wide_df()
    lens_meta = LENS_METADATA[lens]
    return run_investigation(base_df, actions_df, attributions_wide_df, commerce_investigation_config(), primary_metric_name=lens_meta["metric_name"])


@router.get("/experiments/{experiment_id}/investigation", response_model=InvestigationResponse)
def get_investigation(
    experiment_id: str,
    lens: InvestigationLens = Query(..., description="Required: exactly one pre-registered analytical lens. No default — the caller must choose."),
    user: CurrentUser = Depends(get_current_user),
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
