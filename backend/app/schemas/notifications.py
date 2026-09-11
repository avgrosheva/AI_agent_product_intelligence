"""Stage 12 tasks 1-3: request/response contracts for the notification
channel and delivery-log API (backend.app.routers.notifications). A
channel's `url` is write-only — every response carries only
`url_preview` (a short, non-reversible suffix), never the real value
(Stage 12 task 3: "do not log secrets or full webhook URLs" applies to
API responses too, not just log lines)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NotificationChannelCreateRequest(BaseModel):
    channel_type: Literal["webhook", "slack_webhook"]
    url: str = Field(min_length=1)
    enabled: bool = True


class NotificationChannelSchema(BaseModel):
    channel_id: str
    project_id: str
    channel_type: str
    url_preview: str
    enabled: bool
    created_at: datetime


class NotificationChannelListResponse(BaseModel):
    channels: list[NotificationChannelSchema]


class NotificationDeliverySchema(BaseModel):
    notification_id: str
    project_id: str
    channel_id: str
    event_type: str
    dedup_key: str
    payload_summary: str
    status: Literal["pending", "delivered", "failed"]
    attempts: int
    last_error: str | None
    created_at: datetime
    delivered_at: datetime | None


class NotificationDeliveryListResponse(BaseModel):
    deliveries: list[NotificationDeliverySchema]
    total: int
    limit: int
    offset: int
