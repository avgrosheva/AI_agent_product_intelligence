"""Investigation API contracts. Stage 3 review requirement #1: abandonment,
conversion, and constraint-satisfaction are separate pre-registered
analytical lenses, each with its own bounded hypothesis family and its own
BH correction — this module's types make merging them structurally
awkward (every response is scoped to exactly one `lens`), and the router
requires the caller to name one explicitly (no default, no "run all three
and pick the best").
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.app.schemas.common import MetricResultSchema
from backend.app.schemas.experiments import GuardrailCheckSchema

InvestigationLens = Literal["abandonment", "conversion", "constraint_satisfaction"]
LensRole = Literal["primary_regression_lens", "north_star_context", "ai_quality_lens"]

LENS_METADATA: dict[InvestigationLens, dict] = {
    "abandonment": {
        "metric_name": "abandonment_rate",
        "role": "primary_regression_lens",
        "description": "Primary Investigation lens for the current flagship experiment: abandonment shows the clearest aggregate regression (PRD.md SS2).",
    },
    "conversion": {
        "metric_name": "conversion_rate",
        "role": "north_star_context",
        "description": "The business north star; investigated for completeness even though its aggregate movement is currently inconclusive.",
    },
    "constraint_satisfaction": {
        "metric_name": "constraint_satisfaction_rate",
        "role": "ai_quality_lens",
        "description": "AI-quality lens; surfaces effects (e.g. monitor-category constraint interpretation, exploratory-query uplift) that abandonment/conversion do not.",
    },
}


class SegmentFilter(BaseModel):
    """Maps 1:1 onto Sessions-screen query parameters, so a finding can be
    clicked through to the exact sessions that produced it."""

    dimensions: dict[str, str]


class FailureModeShare(BaseModel):
    failure_mode: str
    excess_count: float
    share_of_excess_abandonment: float | None = Field(
        default=None,
        description="Associational only — never a causal claim (Stage 2/3 review causal-language guardrail). None if the segment's total excess abandonment is too small to report a share.",
    )
    raw_share_of_v2_failures: float | None = None


class FailureAttributionSchema(BaseModel):
    n_v1: int
    n_v2: int
    abandonment_rate_v1: float
    abandonment_rate_v2: float
    total_excess_abandonment: float
    reportable: bool
    per_mode: list[FailureModeShare]


class TrajectoryAssociationSchema(BaseModel):
    pattern: str
    n_sessions: int
    pattern_outcome_rate: float
    baseline_outcome_rate: float
    test_name: str
    p_value: float
    bh_significant: bool


class FindingSchema(BaseModel):
    segment_label: str
    segment_filter: SegmentFilter
    n_users_v1: int
    n_users_v2: int
    cluster_mean_v1: float
    cluster_mean_v2: float
    p_value: float
    effect_size_value: float | None
    excess_contribution: float
    dominant_failure_mode: str | None
    failure_attribution: FailureAttributionSchema
    trajectory_associations: list[TrajectoryAssociationSchema]


class RecommendationSchema(BaseModel):
    verdict: Literal["ship", "hold", "roll_back"]
    primary_reason: str
    blocking_guardrails: list[str]
    next_action: str
    rules_applied: list[str]


class ExploredSegmentSummary(BaseModel):
    """Transparency list: segments the scan looked at but that did not
    pass correction/effect-size filtering (INVESTIGATION.md SS3)."""

    segment_label: str
    p_value: float | None
    bh_significant: bool
    meets_min_effect: bool
    verdict: str


class InvestigationResponse(BaseModel):
    experiment_id: str
    lens: InvestigationLens
    lens_role: LensRole
    lens_description: str
    primary_metric: str
    overall: MetricResultSchema
    guardrails: list[GuardrailCheckSchema]
    any_guardrail_breach: bool
    findings: list[FindingSchema]
    explored_not_significant: list[ExploredSegmentSummary]
    recommendation: RecommendationSchema
