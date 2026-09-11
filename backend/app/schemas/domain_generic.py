"""Stage 5: response schemas for the generic, domain-parametrized API
(backend.app.routers.domains). Every field here is generic — no commerce
vocabulary (no "abandonment"/"conversion" lens, no product/recommendation
fields) beyond what backend.app.schemas.investigation's already-generic
nested schemas (FindingSchema, RecommendationSchema, ...) carry over
unchanged from the commerce-only /investigation endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from backend.app.schemas.common import MetricResultSchema
from backend.app.schemas.investigation import ExploredSegmentSummary, FindingSchema, RecommendationSchema


class GenericExperimentSummary(BaseModel):
    experiment_id: str
    name: str
    control_version: str
    treatment_version: str
    start_date: str | None = None
    end_date: str | None = None
    # Stage 16: populated only by list_domain_experiments (never by
    # _experiment_or_404's lookup, which only needs the identity fields
    # above), and only once a project has a persisted primary_metric
    # (backend.project_config) -- exactly the same "primary_metric_configured"
    # gate onboarding-status already reports. A project that hasn't
    # configured one yet sees every experiment as "not_yet_investigated"
    # with no north-star number, rather than this endpoint guessing which
    # metric matters.
    n_sessions: int | None = None
    n_users: int | None = None
    north_star_metric: MetricResultSchema | None = None
    status_chip: Literal["ambiguous_investigate", "no_regression_detected", "not_yet_investigated"] = "not_yet_investigated"


class GenericExperimentListResponse(BaseModel):
    domain: str
    experiments: list[GenericExperimentSummary]


class GenericMetricTableResponse(BaseModel):
    domain: str
    experiment_id: str
    metrics: list[MetricResultSchema]


class GenericGuardrailCheckSchema(BaseModel):
    name: str
    metric: str
    v1_value: float
    v2_value: float
    threshold_description: str
    breached: bool
    severity: Literal["blocking", "warning"]


class GenericGuardrailResponse(BaseModel):
    domain: str
    experiment_id: str
    checks: list[GenericGuardrailCheckSchema]
    any_breach: bool
    any_warning_breach: bool


class GenericInvestigationResponse(BaseModel):
    domain: str
    experiment_id: str
    primary_metric: str
    overall: MetricResultSchema
    guardrails: list[GenericGuardrailCheckSchema]
    any_guardrail_breach: bool
    findings: list[FindingSchema]
    explored_not_significant: list[ExploredSegmentSummary]
    recommendation: RecommendationSchema


class MechanismSchema(BaseModel):
    name: str
    source: Literal["deterministic", "semantic"]
    description: str


class MechanismListResponse(BaseModel):
    domain: str
    mechanisms: list[MechanismSchema]


class SegmentDimensionsResponse(BaseModel):
    """Stage 17 task 3: this domain's own registered pre-treatment
    segment dimensions and their allowed values (backend.core.adapter.
    DomainAdapter.segment_dimensions(), already the exact vocabulary
    Investigation and the sessions-list filter use) -- exposed so the
    frontend can build a filter UI without hardcoding any domain's
    dimension names."""

    domain: str
    dimensions: dict[str, list[str]]


class GenericSessionSummary(BaseModel):
    session_id: str
    agent_version: str
    outcome: str | None = None
    started_at: datetime | None = None
    # Stage 17 task 3: empty for a domain with no attribution storage
    # (support) -- same "empty is valid" contract as everywhere else this
    # shows up (get_domain_mechanisms, get_domain_ai_quality).
    detected_mechanisms: list[str] = []
    review_status: Literal["unreviewed", "confirmed", "rejected", "mixed"] = "unreviewed"


class GenericSessionListResponse(BaseModel):
    domain: str
    items: list[GenericSessionSummary]
    total: int
    limit: int
    offset: int


class GenericToolCallSchema(BaseModel):
    tool_name: str
    success: bool
    error_type: str


class GenericFailureAttributionSchema(BaseModel):
    """Stage 6 task 4: the original detector output (failure_mode,
    detector_source, confidence, evidence_text) plus, alongside it, an
    analyst's review — never merged into or overwriting the former. Empty
    for a domain with no attribution storage (support)."""

    failure_mode: str
    detector_source: str
    confidence: float | None
    evidence_text: str | None
    review_status: Literal["unreviewed", "confirmed", "rejected"] = "unreviewed"
    corrected_mechanism: str | None = None
    review_note: str | None = None


class GenericSessionDetailResponse(BaseModel):
    domain: str
    session_id: str
    outcome: str
    transcript: list[list[str]]  # [[sender, text], ...]
    action_sequence: list[str]
    tool_calls: list[GenericToolCallSchema]
    failure_attributions: list[GenericFailureAttributionSchema] = []


class ReleaseEvaluationSchema(BaseModel):
    evaluation_id: str
    domain: str
    experiment_id: str
    primary_metric: str
    status: Literal["SHIP", "HOLD", "ROLLBACK"]
    evaluated_at: datetime
    has_negative_segment: bool
    any_guardrail_breach: bool
    primary_reason: str
    next_action: str
    key_metrics: dict
    breached_guardrails: list
    top_findings: list
    project_id: str | None = None
    economics: dict | None = None
    raw_status: Literal["SHIP", "HOLD", "ROLLBACK"]
    data_quality_status: Literal["healthy", "warning", "critical"]
    data_quality_gated: bool
    data_window_start: datetime | None = None
    data_window_end: datetime | None = None
    window_hours: int | None = None


class ReleaseHistoryResponse(BaseModel):
    domain: str
    experiment_id: str
    evaluations: list[ReleaseEvaluationSchema]
    total: int
    limit: int
    offset: int


class SessionEvidenceSchema(BaseModel):
    session_id: str
    segment_label: str
    outcome: str
    transcript_excerpt: list[list[str]]
    action_sequence: list[str]


class NegativeSegmentEvidenceSchema(BaseModel):
    segment_label: str
    dimensions: list[str]
    p_value: float | None
    excess_contribution: float | None
    dominant_failure_mode: str | None
    representative_session_ids: list[str]


class LinkedMechanismSchema(BaseModel):
    session_id: str
    failure_mode: str
    detector_source: str
    confidence: float | None
    evidence_text: str | None


class ReleaseEvidenceResponse(BaseModel):
    evaluation_id: str
    domain: str
    experiment_id: str
    status: str
    breached_guardrails: list[dict]
    significant_negative_segments: list[NegativeSegmentEvidenceSchema]
    representative_sessions: list[SessionEvidenceSchema]
    linked_failure_mechanisms: list[LinkedMechanismSchema]


class GenericFunnelStagePoint(BaseModel):
    stage: str
    n_sessions: int
    conversion_from_previous: float | None = None


class GenericFunnelSeries(BaseModel):
    agent_version: str
    n_sessions: int
    stages: list[GenericFunnelStagePoint]


class GenericFunnelResponse(BaseModel):
    """Stage 16: the funnel concept (impression->click->cart->purchase) is
    inherently commerce-shaped. `applicable=False` (empty `series`) for any
    domain whose data has none of the funnel-stage columns -- the same
    "empty concept is valid" pattern as an empty mechanism registry, not an
    error and not a fabricated funnel."""

    domain: str
    experiment_id: str
    applicable: bool
    series: list[GenericFunnelSeries]


class GenericFailureMechanismPrevalenceItem(BaseModel):
    failure_mode: str
    detector_source: str
    count_v1: int
    count_v2: int
    rate_v1: float
    rate_v2: float
    reviewed_count: int = 0
    confirmed_count: int = 0
    rejected_count: int = 0


class GenericToolUseQuality(BaseModel):
    """Null fields, not zeros, where a domain's ingested data doesn't carry
    that column at all (e.g. no per-arm tool error rate for support) --
    the same graceful-degradation contract as backend.economics.compute."""

    tool_calls_per_session_v1: float | None
    tool_calls_per_session_v2: float | None
    tool_success_rate_v1: float | None
    tool_success_rate_v2: float | None
    tool_error_rate_v1: float | None
    tool_error_rate_v2: float | None


class GenericTrajectoryPatternItem(BaseModel):
    pattern: str
    n_sessions_v1: int
    n_sessions_v2: int
    negative_outcome_rate_v1: float
    negative_outcome_rate_v2: float


class GenericAIQualitySummaryResponse(BaseModel):
    domain: str
    experiment_id: str
    failure_mechanism_prevalence: list[GenericFailureMechanismPrevalenceItem]
    tool_use_quality: GenericToolUseQuality
    trajectory_patterns: list[GenericTrajectoryPatternItem]


class DataQualityCheckSchema(BaseModel):
    name: str
    value: float | None
    status: Literal["healthy", "warning", "critical", "not_applicable"]
    detail: str


class DataQualityReportResponse(BaseModel):
    project_id: str
    domain: str
    status: Literal["healthy", "warning", "critical"]
    generated_at: datetime
    checks: list[DataQualityCheckSchema]
