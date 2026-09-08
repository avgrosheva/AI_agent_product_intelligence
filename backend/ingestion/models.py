"""Generic ingestion storage (Stage 3). Deliberately separate tables from
the commerce domain's sessions/messages/agent_actions/tool_calls/
recommendations/product_events — an external, non-commerce agent team's
data is never forced into those commerce-shaped tables (Stage 3 task 3).

Every "vocabulary" column that was a Postgres-native ENUM on the commerce
schema (outcome, action_type, tool_name, sender) is plain TEXT here,
validated only at the Pydantic ingestion-contract layer (backend.ingestion
.schemas), not locked into a fixed set at the database level — this is the
concrete fix for the DB-enum coupling Stage 2's audit identified as the
biggest blocker to a second domain storing its own vocabulary.

Idempotency: every row's primary key is a deterministic UUID5 derived from
(domain, external_id) — see ids.py — so re-ingesting the same external ID
resolves to the same row and the ingestion service's upsert
(INSERT ... ON CONFLICT DO UPDATE) updates it in place rather than
duplicating it. Each table also carries an explicit UNIQUE constraint on
its (parent, external_id) pair as a second, DB-enforced guarantee.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class IngestedExperiment(Base):
    __tablename__ = "ingested_experiments"

    experiment_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    external_experiment_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    control_version: Mapped[str] = mapped_column(Text, nullable=False)
    treatment_version: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (UniqueConstraint("domain", "external_experiment_id", name="uq_ingested_experiments_domain_external_id"),)


class IngestedSession(Base):
    __tablename__ = "ingested_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    external_session_id: Mapped[str] = mapped_column(Text, nullable=False)
    experiment_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ingested_experiments.experiment_id"), nullable=False, index=True)
    agent_version: Mapped[str] = mapped_column(Text, nullable=False)
    external_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    outcome_label: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (UniqueConstraint("domain", "external_session_id", name="uq_ingested_sessions_domain_external_id"),)


class IngestedMessage(Base):
    __tablename__ = "ingested_messages"

    message_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ingested_sessions.session_id"), nullable=False, index=True)
    external_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (UniqueConstraint("session_id", "external_message_id", name="uq_ingested_messages_session_external_id"),)


class IngestedAction(Base):
    __tablename__ = "ingested_actions"

    action_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ingested_sessions.session_id"), nullable=False, index=True)
    external_action_id: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("session_id", "external_action_id", name="uq_ingested_actions_session_external_id"),)


class IngestedToolCall(Base):
    __tablename__ = "ingested_tool_calls"

    tool_call_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    action_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ingested_actions.action_id"), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ingested_sessions.session_id"), nullable=False, index=True)
    external_tool_call_id: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (UniqueConstraint("action_id", "external_tool_call_id", name="uq_ingested_tool_calls_action_external_id"),)


class IngestedMetric(Base):
    """One named numeric metric per session — covers both the outcome
    label's own optional metrics and session-level business/quality
    signals (Stage 3 task 1's "optional business metrics / quality
    signals") uniformly, since both are just (name, value) pairs from the
    ingestion contract's point of view."""

    __tablename__ = "ingested_metrics"

    metric_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ingested_sessions.session_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (UniqueConstraint("session_id", "name", name="uq_ingested_metrics_session_name"),)
