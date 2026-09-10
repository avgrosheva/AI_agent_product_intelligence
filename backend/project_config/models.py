"""Stage 12 task 4: one row per project — every field independently
nullable/omittable, since a project may override only some of a domain's
static defaults (or none at all)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class ProjectConfig(Base):
    __tablename__ = "project_configs"

    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    primary_metric: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {"metrics": [...]} — the exact shape backend.core.config.load_metric_config_from_dict expects.
    metrics_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"guardrails": [...]} — backend.core.config.load_guardrail_config_from_dict.
    guardrails_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {dimension_name: [allowed values]} — DomainAdapter.segment_dimensions()'s own shape.
    segment_dimensions_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"cost_column":..., "success_column":..., "value_column":...} — backend.economics.config.EconomicsConfig's fields.
    economics_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    monitoring_cadence_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Flat list of enabled event-type strings (ROLLBACK, HOLD,
    # BLOCKING_GUARDRAIL_BREACH, CRITICAL_DATA_QUALITY,
    # MONITORING_JOB_FAILURE) -- deliberately not a rules DSL: every
    # enabled channel gets every enabled event type, nothing fancier.
    enabled_notification_rules: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
