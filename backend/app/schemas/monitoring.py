"""Stage 11 tasks 1-2/7: request/response contracts for the monitoring
configuration and run-history API (backend.app.routers.monitoring)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MonitoringConfigCreateRequest(BaseModel):
    domain: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    primary_metric: str = Field(min_length=1)
    cadence_seconds: int = Field(gt=0, description="How often this config is eligible to run again, in seconds.")
    window_hours: int | None = Field(default=None, gt=0, description="Optional monitoring window, in hours, recorded on each run for reporting.")
    enabled: bool = True


class MonitoringConfigSchema(BaseModel):
    config_id: str
    project_id: str
    domain: str
    experiment_id: str
    primary_metric: str
    cadence_seconds: int
    window_hours: int | None
    enabled: bool
    created_at: datetime


class MonitoringConfigListResponse(BaseModel):
    configs: list[MonitoringConfigSchema]


class MonitoringRunSchema(BaseModel):
    run_id: str
    config_id: str | None
    project_id: str
    domain: str
    experiment_id: str
    primary_metric: str
    status: Literal["running", "succeeded", "failed", "skipped_duplicate"]
    started_at: datetime
    completed_at: datetime | None
    data_window_start: datetime | None
    data_window_end: datetime | None
    release_evaluation_id: str | None
    failure_reason: str | None


class MonitoringRunListResponse(BaseModel):
    runs: list[MonitoringRunSchema]


class MonitoringRunTriggerResponse(BaseModel):
    """Stage 11 task 1: the on-demand trigger endpoint dispatches the
    actual evaluation as a background task and returns immediately — it
    never blocks the request on the Investigation engine. Poll
    /configs/{id}/latest or /configs/{id}/runs to see the resulting run."""

    config_id: str
    message: str = "Monitoring run accepted and scheduled to run in the background."
