"""Stage 11 task 5: a small audit log both the Langfuse and Postgres
business-data connectors write one row to after every `import`-mode call
(never for a `dry_run`) — the only source backend.quality.service reads
for "unmatched business-data rate", "duplicate/conflicting data rate",
and "connector import failures". Never computed any other way, so the
data-quality report can never show a number the connectors didn't
actually report."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class ConnectorRun(Base):
    __tablename__ = "connector_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    connector: Mapped[str] = mapped_column(Text, nullable=False)  # "langfuse" | "postgres_business"
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rows_fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unmatched_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validation_error_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
