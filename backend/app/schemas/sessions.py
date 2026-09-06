from __future__ import annotations

from datetime import datetime

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
    failure_mode: str | None = None


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
    failure_mode: str
    confidence: float
    evidence_text: str
    source: str
    provenance: ClassifierProvenance


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
    failure_classification: FailureClassificationSchema | None
