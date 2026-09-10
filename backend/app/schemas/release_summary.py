"""Stage 14: response schema for the release-summary endpoint
(backend.app.routers.domains) — the one endpoint a UI needs for a
complete decision screen (task 5), built from backend.release.summary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DecisionSummarySchema(BaseModel):
    evaluation_id: str
    domain: str
    experiment_id: str
    primary_metric: str
    verdict: Literal["SHIP", "HOLD", "ROLLBACK"]
    raw_verdict: Literal["SHIP", "HOLD", "ROLLBACK"]
    primary_reason: str
    primary_metric_v1: float | None
    primary_metric_v2: float | None
    primary_metric_delta: float | None
    primary_metric_p_value: float | None
    breached_guardrails: list[dict]
    significant_negative_segment_count: int
    data_quality_status: Literal["healthy", "warning", "critical"]
    data_quality_gated: bool
    economics_impact: float | None
    confidence: Literal["strong", "moderate", "weak", "insufficient_evidence"]


class EvidenceItemSchema(BaseModel):
    rank: int
    category: str
    summary: str


class FindingExplanationSchema(BaseModel):
    segment_label: str
    dimensions: list[str]
    metric: str
    v1_value: float | None
    v2_value: float | None
    delta: float | None
    p_value: float | None
    excess_contribution: float | None
    dominant_failure_mode: str | None
    representative_session_ids: list[str]
    next_action: str


class SessionEvidenceDetailSchema(BaseModel):
    session_id: str
    segment_label: str
    outcome: str
    transcript_excerpt: list[list[str]]
    action_sequence: list[str]
    detected_mechanisms: list[str]
    human_review_status: Literal["reviewed", "not_reviewed"]
    selected_because: str


class MonitoringWindowInfoSchema(BaseModel):
    data_window_start: datetime | None
    data_window_end: datetime | None
    window_hours: int | None


class ReleaseSummaryResponse(BaseModel):
    decision: DecisionSummarySchema
    explanation_text: str
    evidence_hierarchy: list[EvidenceItemSchema]
    findings: list[FindingExplanationSchema]
    representative_sessions: list[SessionEvidenceDetailSchema]
    economics: dict | None
    data_quality_status: Literal["healthy", "warning", "critical"]
    monitoring_window: MonitoringWindowInfoSchema
