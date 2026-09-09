"""Generic release-evaluation history storage (Stage 5 task 3). One row
per on-demand evaluation of one (domain, experiment_id, primary_metric)
triple — a append-only log, never updated in place, so "release history"
is just "every row for this triple, newest first."

Deliberately a separate table from both the commerce ORM models and the
Stage 3 ingestion tables: it stores an EVALUATION RESULT (a snapshot of
what the Investigation engine concluded at one point in time), not raw
domain data, and applies identically regardless of which domain or which
underlying storage (commerce's own tables, or the generic ingestion
tables) that domain's DomainAdapter reads from.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class ReleaseEvaluation(Base):
    __tablename__ = "release_evaluations"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # Text, not a UUID FK: experiment_id may come from either commerce's
    # `experiments` table or the generic `ingested_experiments` table
    # depending on domain, and this log must not depend on which.
    experiment_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    primary_metric: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # "SHIP" | "HOLD" | "ROLLBACK"
    evaluated_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    has_negative_segment: Mapped[bool] = mapped_column(Boolean, nullable=False)
    any_guardrail_breach: Mapped[bool] = mapped_column(Boolean, nullable=False)
    primary_reason: Mapped[str] = mapped_column(Text, nullable=False)
    next_action: Mapped[str] = mapped_column(Text, nullable=False)
    key_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    breached_guardrails: Mapped[list] = mapped_column(JSONB, nullable=False)
    top_findings: Mapped[list] = mapped_column(JSONB, nullable=False)
