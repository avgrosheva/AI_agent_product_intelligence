from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ReviewRequest(BaseModel):
    decision: Literal["confirmed", "rejected"]
    corrected_mechanism: str | None = None
    note: str | None = None
    reviewer: str | None = None


class ReviewSchema(BaseModel):
    review_id: str
    domain: str
    project_id: str | None = None
    session_id: str
    failure_mode: str
    decision: Literal["confirmed", "rejected"]
    corrected_mechanism: str | None
    note: str | None
    reviewer: str | None
    created_at: datetime
    updated_at: datetime


class SessionReviewsResponse(BaseModel):
    domain: str
    session_id: str
    reviews: list[ReviewSchema]


class ReviewQueueItemSchema(BaseModel):
    session_id: str
    experiment_id: str
    agent_version: str
    failure_mode: str
    detector_source: str
    confidence: float | None
    evidence_text: str | None
    reviewed: bool
    high_impact: bool = False
    # Stage 19 task 6/8: provenance + why this item was prioritized.
    detector_version: str = ""
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    is_newest_version: bool = False


class ReviewQueueResponse(BaseModel):
    domain: str
    items: list[ReviewQueueItemSchema]
    total: int
    limit: int
    offset: int
