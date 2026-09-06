from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from backend.app.schemas.common import MetricResultSchema


class ExperimentSummary(BaseModel):
    """Overview screen card (PRD.md SS4 step 1)."""

    experiment_id: str
    name: str
    control_version: str
    treatment_version: str
    start_date: date
    end_date: date
    status: str
    n_sessions: int
    n_users: int
    north_star_metric: MetricResultSchema
    status_chip: Literal["ambiguous_investigate", "no_regression_detected", "not_yet_investigated"]


class ExperimentListResponse(BaseModel):
    experiments: list[ExperimentSummary]


class ExperimentDetail(BaseModel):
    experiment_id: str
    name: str
    control_version: str
    treatment_version: str
    start_date: date
    end_date: date
    status: str
    traffic_split: float
    n_sessions_v1: int
    n_sessions_v2: int
    n_users_v1: int
    n_users_v2: int


class MetricTableResponse(BaseModel):
    experiment_id: str
    metrics: list[MetricResultSchema]


class FunnelStep(BaseModel):
    agent_version: Literal["v1", "v2"]
    n_sessions: int
    n_impression: int
    n_click: int
    n_cart: int
    n_purchase: int
    impression_to_click_rate: float | None
    click_to_cart_rate: float | None
    cart_to_purchase_rate: float | None


class FunnelResponse(BaseModel):
    experiment_id: str
    funnel: list[FunnelStep]


class GuardrailCheckSchema(BaseModel):
    name: str
    v1_value: float
    v2_value: float
    threshold_description: str
    breached: bool


class GuardrailResponse(BaseModel):
    experiment_id: str
    checks: list[GuardrailCheckSchema]
    any_breach: bool
