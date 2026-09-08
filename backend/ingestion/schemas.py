"""Generic ingestion contract (Stage 3 task 1). JSON-friendly, stable
external IDs throughout — every entity an external agent team sends is
identified by an `external_*_id` string it controls, never by an
internally-generated ID, so re-sending the same data is safe (idempotent)
and no round trip is needed to learn an assigned ID before sending
children (messages/actions/tool calls) that reference a session.

No field here is commerce-specific: `outcome.label`, `agent_version`,
`sender`, and `action_type` are free-form strings, not a fixed enum — a
domain defines its own vocabulary for these (a support-agent domain might
use outcome labels like "resolved"/"escalated"; commerce uses "purchase"/
"abandoned"). `context` is an opaque JSON object for whatever
domain-specific payload a detector might need (e.g. commerce's stated
constraints, or a support ticket's category) — the generic core never
reads it; only a domain adapter interprets it.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class IngestExperiment(BaseModel):
    external_experiment_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    control_version: str = Field(min_length=1)
    treatment_version: str = Field(min_length=1)
    start_date: date | None = None
    end_date: date | None = None


class IngestToolCall(BaseModel):
    external_tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    success: bool
    error_type: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    input: dict | None = None
    output: dict | None = None


class IngestAction(BaseModel):
    external_action_id: str = Field(min_length=1)
    sequence_index: int = Field(ge=0)
    action_type: str = Field(min_length=1)
    started_at: datetime
    latency_ms: int | None = Field(default=None, ge=0)
    tool_calls: list[IngestToolCall] = Field(default_factory=list)


class IngestMessage(BaseModel):
    external_message_id: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    sender: str = Field(min_length=1)
    text: str
    created_at: datetime


class IngestMetric(BaseModel):
    """One named numeric signal — a business metric (e.g. "revenue_usd")
    or a quality signal (e.g. "csat_score"). The domain adapter decides
    which registered metric names it recognizes; ingestion itself accepts
    any name."""

    name: str = Field(min_length=1)
    value: float


class IngestOutcome(BaseModel):
    label: str = Field(min_length=1)
    metrics: list[IngestMetric] = Field(default_factory=list)


class IngestSession(BaseModel):
    external_session_id: str = Field(min_length=1)
    external_experiment_id: str = Field(min_length=1)
    agent_version: str = Field(min_length=1)
    external_user_id: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    messages: list[IngestMessage] = Field(default_factory=list)
    actions: list[IngestAction] = Field(default_factory=list)
    outcome: IngestOutcome
    metrics: list[IngestMetric] = Field(default_factory=list)
    context: dict | None = None

    @field_validator("messages")
    @classmethod
    def _unique_message_ids(cls, v: list[IngestMessage]) -> list[IngestMessage]:
        ids = [m.external_message_id for m in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate external_message_id within one session")
        return v

    @field_validator("actions")
    @classmethod
    def _unique_action_ids(cls, v: list[IngestAction]) -> list[IngestAction]:
        ids = [a.external_action_id for a in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate external_action_id within one session")
        for action in v:
            tool_ids = [tc.external_tool_call_id for tc in action.tool_calls]
            if len(tool_ids) != len(set(tool_ids)):
                raise ValueError(f"duplicate external_tool_call_id within action {action.external_action_id!r}")
        return v


class IngestBatchRequest(BaseModel):
    """`domain` selects which registered DomainAdapter will later interpret
    this data (backend.core.adapter.DomainAdapter) — it does not need to
    exist yet at ingestion time; ingestion only stores the data. Every
    experiment referenced by a session must also appear in `experiments`
    within the same request (or have been ingested by an earlier request)."""

    domain: str = Field(min_length=1)
    experiments: list[IngestExperiment] = Field(default_factory=list)
    sessions: list[IngestSession]

    @field_validator("sessions")
    @classmethod
    def _unique_session_ids(cls, v: list[IngestSession]) -> list[IngestSession]:
        ids = [s.external_session_id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate external_session_id within one batch")
        return v


class IngestionErrorDetail(BaseModel):
    session_index: int | None = None
    external_session_id: str | None = None
    message: str


class IngestionResponse(BaseModel):
    domain: str
    experiments_ingested: int
    sessions_ingested: int
    messages_ingested: int
    actions_ingested: int
    tool_calls_ingested: int
    metrics_ingested: int
