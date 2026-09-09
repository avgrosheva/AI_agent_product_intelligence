from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AlertSchema(BaseModel):
    alert_id: str
    domain: str
    experiment_id: str
    evaluation_id: str
    rule: Literal["rollback", "blocking_guardrail_breach", "hold_negative_segment"]
    severity: Literal["critical", "warning"]
    reason: str
    related_guardrail: str | None
    related_finding: str | None
    status: Literal["open", "acknowledged"]
    created_at: datetime
    acknowledged_at: datetime | None


class AlertListResponse(BaseModel):
    alerts: list[AlertSchema]
