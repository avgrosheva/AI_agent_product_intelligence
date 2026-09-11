from __future__ import annotations

from pydantic import BaseModel

from backend.app.schemas.common import ClassifierProvenance


class FailureMechanismPrevalenceItem(BaseModel):
    """Share of sessions where this mechanism's detector fired
    detected=true. NOT an exclusive distribution — mechanisms can overlap,
    so rate_v1/rate_v2 across all items do not sum to 1.0 (hybrid
    multi-label redesign)."""

    failure_mode: str
    detector_source: str  # "deterministic" | "real_llm" | "mock_llm"
    count_v1: int
    count_v2: int
    rate_v1: float
    rate_v2: float
    # Stage 6 task 4: how much of this mechanism's detected=true population
    # (across both arms) an analyst has reviewed and what they decided —
    # counts, never a modification of count_v1/count_v2/rate_v1/rate_v2
    # above, which stay the original detector output.
    reviewed_count: int = 0
    confirmed_count: int = 0
    rejected_count: int = 0


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
    # Stage 16: the CURRENT architecture's own evaluation, additive and
    # independent of the fields above (which are the deprecated exclusive
    # classifier's shape, kept only for that historical evaluation path —
    # AI_EVALUATION.md SS2). None until a hybrid benchmark has been run
    # and its summary committed to reports/final/.
    hybrid_evaluation: HybridEvaluationSummary | None = None


class DeterministicDetectorMetric(BaseModel):
    failure_mode: str
    precision: float
    recall: float
    f1: float
    support: int


class SemanticMechanismMetric(BaseModel):
    failure_mode: str
    precision: float
    recall: float
    f1: float
    support: int
    mean_confidence_correct: float | None
    mean_confidence_incorrect: float | None


class HybridEvaluationSummary(BaseModel):
    """Stage 16: the current hybrid multi-label attribution pipeline's own
    evaluation (AI_EVALUATION.md SS5) — a held-out benchmark against
    independent multi-label ground truth, distinct in shape from
    ClassifierEvaluationResponse's per_class_metrics/acceptance_bars above
    (which target the deprecated exclusive classifier). Read from
    scripts/run_hybrid_benchmark.py's persisted output, never recomputed
    here."""

    subset: str
    provider: str
    model: str
    prompt_version: str
    detector_version: str
    evaluation_seed: int
    subset_size: int
    deterministic_detectors: list[DeterministicDetectorMetric]
    deterministic_detectors_note: str
    semantic_metrics: list[SemanticMechanismMetric]
    semantic_micro_precision: float
    semantic_micro_recall: float
    semantic_micro_f1: float
    semantic_macro_f1: float
    semantic_exact_match_ratio: float
    semantic_hamming_loss: float
    semantic_coverage: float
    evaluated_at: str | None


class AIQualitySummaryResponse(BaseModel):
    experiment_id: str
    failure_mechanism_prevalence: list[FailureMechanismPrevalenceItem]
    tool_use_quality: ToolUseQualitySchema
    trajectory_patterns: list[TrajectoryPatternFrequencyItem]
    classifier_provenance: ClassifierProvenance
