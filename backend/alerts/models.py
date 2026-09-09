"""Generic alert storage (Stage 6 task 2). One row per distinct triggered
condition on one release evaluation — see backend.alerts.rules for what
"distinct" means (the dedup key). Never updated except status/
acknowledged_at when an analyst acknowledges it."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    experiment_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    evaluation_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule: Mapped[str] = mapped_column(Text, nullable=False)  # "rollback" | "blocking_guardrail_breach" | "hold_negative_segment"
    severity: Mapped[str] = mapped_column(Text, nullable=False)  # "critical" | "warning"
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    related_guardrail: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_finding: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, index=True)  # "open" | "acknowledged"
    created_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(nullable=True)
