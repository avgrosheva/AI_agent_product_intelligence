from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditLogEntrySchema(BaseModel):
    entry_id: str
    actor_user_id: str | None
    actor_email: str | None
    org_id: str | None
    project_id: str | None
    action: str
    target: str | None
    created_at: datetime
    metadata: dict


class AuditLogListResponse(BaseModel):
    entries: list[AuditLogEntrySchema]
    total: int
    limit: int
    offset: int
