"""Stage 12 tasks 1/3: notification channels (a project's own webhook/
Slack destinations) and the append-only delivery log every dispatch
attempt writes to. `NotificationChannel.url` is the one field that must
never be returned by an API response or written into a log line —
enforced at the service/schema layer, not here (the column itself has to
hold the real value to make the HTTP call)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    channel_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    channel_type: Mapped[str] = mapped_column(Text, nullable=False)  # "webhook" | "slack_webhook"
    url: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    notification_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # pending | delivered | failed
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Stage 12 task 8 ("notification deduplication"): the same real-world
    # event (same evaluation_id/run_id, encoded in dedup_key) delivered to
    # the same channel must never produce two rows -- a DB-level guarantee,
    # not just an application-level check-then-insert race.
    __table_args__ = (UniqueConstraint("project_id", "channel_id", "event_type", "dedup_key", name="uq_notification_delivery_dedup"),)
