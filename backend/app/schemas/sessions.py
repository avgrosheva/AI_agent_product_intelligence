from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from backend.app.schemas.common import ClassifierProvenance


class SessionSummary(BaseModel):
    session_id: str
    agent_version: str
    requested_category: str
    constraint_count_bucket: str
    platform: str
    device_tier: str
    locale: str
    persona: str
    outcome: str
    num_turns: int
    total_latency_ms: int
    total_cost_usd: float
    started_at: datetime
    detected_failure_modes: list[str] = []


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    total: int
    limit: int
    offset: int
    filters_applied: dict[str, str]


class MessageSchema(BaseModel):
    turn_index: int
    sender: str
    text: str
    tokens: int
    latency_ms: int | None
    created_at: datetime


class AgentActionSchema(BaseModel):
    """Observable action only — never hidden chain-of-thought (Stage 4 constraint)."""

    sequence_index: int
    action_type: str
    latency_ms: int
    model_name: str
    started_at: datetime


class ToolCallSchema(BaseModel):
    """Coarse abstraction level only — no raw input/output JSON blobs."""

    tool_name: str
    success: bool
    error_type: str
    latency_ms: int
    action_sequence_index: int
    action_started_at: datetime


class RecommendationItemSchema(BaseModel):
    product_id: str
    rank_position: int
    clicked: bool
    satisfies_constraints: bool


class ProductEventSchema(BaseModel):
    event_type: str
    event_time: datetime
    price_at_event: int


class EvaluationSchema(BaseModel):
    """Deterministic, rule-based evaluations only (AI_EVALUATION.md SS6) —
    answer_faithfulness (LLM-judged) is absent until Stage 3+'s classifier
    covers it; evaluator field makes the provenance explicit either way."""

    eval_type: str
    score: float
    evaluator: str


class FailureClassificationSchema(BaseModel):
    """One detected mechanism (hybrid multi-label redesign) — a session's
    SessionDetailResponse carries a list of these, one per mechanism that
    actually fired, not a single exclusive classification.

    Stage 6 task 4: review_status/corrected_mechanism/review_note surface
    an analyst's decision (backend.review) alongside the original,
    unmodified detector output above — the review is never merged into or
    used to overwrite failure_mode/confidence/evidence_text."""

    failure_mode: str
    detector_source: str  # "deterministic" | "real_llm" | "mock_llm"
    confidence: float | None
    evidence_text: str | None
    provenance: ClassifierProvenance
    review_status: Literal["unreviewed", "confirmed", "rejected"] = "unreviewed"
    corrected_mechanism: str | None = None
    review_note: str | None = None


class SessionDetailResponse(BaseModel):
    session_id: str
    agent_version: str
    requested_category: str
    constraint_count_bucket: str
    platform: str
    device_tier: str
    locale: str
    persona: str
    num_constraints: int
    outcome: str
    num_turns: int
    total_latency_ms: int
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    started_at: datetime
    ended_at: datetime | None

    transcript: list[MessageSchema]
    agent_actions: list[AgentActionSchema]
    tool_calls: list[ToolCallSchema]
    recommendations: list[RecommendationItemSchema]
    product_events: list[ProductEventSchema]
    evaluations: list[EvaluationSchema]
    failure_attributions: list[FailureClassificationSchema]
