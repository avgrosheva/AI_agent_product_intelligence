"""recommendations, product_events, evaluations, failure_labels (DATA_MODEL.md SS3.8-3.11)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base
from backend.app.models.enums import (
    DetectorSource,
    EvalType,
    Evaluator,
    FailureLabelSource,
    FailureMechanism,
    FailureMode,
    ProductEventType,
)
from backend.app.models.pg_enum import pg_enum


class Recommendation(Base):
    __tablename__ = "recommendations"

    rec_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.product_id"), nullable=False, index=True
    )
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    shown_at: Mapped[datetime] = mapped_column(nullable=False)
    clicked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    clicked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    satisfies_constraints: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ProductEvent(Base):
    __tablename__ = "product_events"

    event_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.product_id"), nullable=False, index=True
    )
    event_type: Mapped[ProductEventType] = mapped_column(
        pg_enum(ProductEventType, "product_event_type_enum"), nullable=False
    )
    event_time: Mapped[datetime] = mapped_column(nullable=False)
    price_at_event: Mapped[int] = mapped_column(Integer, nullable=False)


class Evaluation(Base):
    __tablename__ = "evaluations"

    eval_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    eval_type: Mapped[EvalType] = mapped_column(pg_enum(EvalType, "eval_type_enum"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    evaluator: Mapped[Evaluator] = mapped_column(pg_enum(Evaluator, "evaluator_enum"), nullable=False)
    rationale_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class FailureLabel(Base):
    """Application-visible failure labels only.

    Stage 1 leaves this table empty: real classification (LLM or
    rule-based mock client) is Stage 3 work (AI_EVALUATION.md, ROADMAP.md
    Stage 3). `source` has a single legal value in the app database —
    ground-truth labels are never written here (DATA_MODEL.md SS3.11, SS8).
    """

    __tablename__ = "failure_labels"

    label_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    failure_mode: Mapped[FailureMode] = mapped_column(
        pg_enum(FailureMode, "failure_mode_enum"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[FailureLabelSource] = mapped_column(
        pg_enum(FailureLabelSource, "failure_label_source_enum"),
        nullable=False,
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class SessionFailureAttribution(Base):
    """Hybrid multi-label failure attribution (supersedes FailureLabel).

    One row per (session_id, failure_mode) pair, for each of the six
    FailureMechanism values — including detected=False rows, so
    "none = no mechanism fired" is always derivable from the absence of any
    detected=True row for a session, never itself a stored prediction.
    `detector_source` distinguishes a deterministic rule (confidence/
    evidence_text/provider/model/prompt_version all null — a deterministic
    rule doesn't have a confidence score or a model) from a real or mock
    LLM call (those fields populated). Ground truth is never written here —
    it lives only in validation_ground_truth.parquet, offline.
    """

    __tablename__ = "session_failure_attributions"

    attribution_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    failure_mode: Mapped[FailureMechanism] = mapped_column(
        pg_enum(FailureMechanism, "failure_mechanism_enum"), nullable=False
    )
    detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detector_source: Mapped[DetectorSource] = mapped_column(
        pg_enum(DetectorSource, "detector_source_enum"), nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    detector_version: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "failure_mode", name="uq_session_failure_attributions_session_mode"),
    )
