"""Monitoring configuration and run-history storage (Stage 11 tasks 1-2).

`monitoring_configs`: what to check, on what cadence — one row per
(project, experiment, primary_metric) a caller has asked to watch.

`monitoring_runs`: an append-only log of every execution of a config (or
an ad-hoc on-demand run with no saved config, hence `config_id` is
nullable) — started_at/completed_at, status, the data window considered,
the resulting release_evaluation_id, and a failure_reason when the job
raised. Never updated to hide a failure; a new row is only ever added.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class MonitoringConfig(Base):
    __tablename__ = "monitoring_configs"

    config_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    experiment_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    primary_metric: Mapped[str] = mapped_column(Text, nullable=False)
    cadence_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    window_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    config_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    experiment_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    primary_metric: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # running | succeeded | failed | skipped_duplicate
    started_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    data_window_start: Mapped[datetime | None] = mapped_column(nullable=True)
    data_window_end: Mapped[datetime | None] = mapped_column(nullable=True)
    # Stage 13 task 5: the config's window_hours AT THE TIME this run
    # executed — self-contained provenance on the run row itself, not
    # just inferable from the (possibly since-changed) config.
    window_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_evaluation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
