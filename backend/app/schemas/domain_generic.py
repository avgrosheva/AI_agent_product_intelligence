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


class GenericSessionSummary(BaseModel):
    session_id: str
    agent_version: str
    outcome: str | None = None
    started_at: datetime | None = None


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


class ReleaseHistoryResponse(BaseModel):
    domain: str
    experiment_id: str
    evaluations: list[ReleaseEvaluationSchema]
