from __future__ import annotations

from pydantic import BaseModel

from backend.app.schemas.common import ClassifierProvenance


class FailureModeDistributionItem(BaseModel):
    failure_mode: str
    count_v1: int
    count_v2: int
    rate_v1: float
    rate_v2: float


class ToolUseQualitySchema(BaseModel):
    tool_calls_per_session_v1: float
    tool_calls_per_session_v2: float
    tool_success_rate_v1: float
    tool_success_rate_v2: float
    tool_error_rate_v1: float
    tool_error_rate_v2: float


class TrajectoryPatternFrequencyItem(BaseModel):
    """Descriptive frequency + outcome-rate pairing only (METRICS.md's
    "not an observability platform" stance: always paired with an outcome
    column) — NOT a statistically-tested Investigation finding."""

    pattern: str
    n_sessions_v1: int
    n_sessions_v2: int
    abandonment_rate_v1: float
    abandonment_rate_v2: float


class ClassifierPerClassMetric(BaseModel):
    failure_mode: str
    support: int
    precision: float | None
    recall: float | None
    f1: float | None


class ClassifierAcceptanceBar(BaseModel):
    failure_mode: str
    recall: float
    recall_bar: float
    recall_pass: bool
    precision: float
    precision_bar: float
    precision_pass: bool


class ClassifierEvaluationResponse(BaseModel):
    provenance: ClassifierProvenance
    n_sessions_evaluated: int | None
    overall_accuracy: float | None
    mean_confidence_correct: float | None
    mean_confidence_incorrect: float | None
    per_class_metrics: list[ClassifierPerClassMetric]
    acceptance_bars: list[ClassifierAcceptanceBar]
    all_acceptance_bars_met: bool | None


class AIQualitySummaryResponse(BaseModel):
    experiment_id: str
    failure_mode_distribution: list[FailureModeDistributionItem]
    tool_use_quality: ToolUseQualitySchema
    trajectory_patterns: list[TrajectoryPatternFrequencyItem]
    classifier_provenance: ClassifierProvenance
