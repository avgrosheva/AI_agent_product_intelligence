"""Shared response schemas (PRD.md: "no frontend calculations of analytical
metrics" — every number here is already computed by backend.analytics /
backend.investigation before it reaches a schema constructor).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SemanticClass = Literal["pre_treatment", "treatment", "post_treatment_mechanism", "outcome", "economic_outcome"]
Verdict = Literal["significant", "not_significant", "insufficient_evidence"]


class MetricResultSchema(BaseModel):
    """One row of the Stage 2 experiment-results table
    (backend.analytics.experiment_results.MetricResult), unmodified.

    Descriptive vs. inferential distinction is preserved explicitly: the
    `session_value_*` fields are session-level descriptive numbers; the
    `cluster_*`/`p_value`/`ci_*`/`effect_size_*` fields are the per-user
    cluster-level inferential result (STATISTICS.md SS2). A client must not
    treat the descriptive value as if it carried a significance verdict.
    """

    model_config = ConfigDict(from_attributes=True)

    metric_name: str
    segment: str
    semantic_class: SemanticClass
    is_descriptive: bool = True
    is_inferential: bool

    n_sessions_v1: int
    n_sessions_v2: int
    session_value_v1: float
    session_value_v2: float

    n_users_v1: int = 0
    n_users_v2: int = 0
    cluster_mean_v1: float | None = None
    cluster_mean_v2: float | None = None
    event_count_v1: int | None = None
    event_count_v2: int | None = None
    non_event_count_v1: int | None = None
    non_event_count_v2: int | None = None

    test_name: str | None = None
    p_value: float | None = None
    effect_size_name: str | None = None
    effect_size_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    ci_stat: str | None = None

    verdict: Verdict
    notes: list[str] = Field(default_factory=list)


class ClassifierProvenance(BaseModel):
    """Stage 3 review requirement #2: any response surfacing
    classifier-derived data must carry this, and a mock classifier's
    numbers must never be presentable as real-LLM performance.

    provider/model are populated only when classifier_type == "real_llm"
    (e.g. provider="openrouter", model="anthropic/claude-sonnet-5"),
    parsed from classifier_version — see
    backend.llm.provenance.parse_real_llm_version. Both are None for the
    mock and for the not-yet-classified states."""

    classifier_type: Literal["rule_based_mock", "real_llm", "unknown", "not_classified"]
    classifier_version: str | None = None
    provider: str | None = None
    model: str | None = None
    is_mock: bool
    evaluation_status: Literal["evaluated_current", "evaluated_stale", "not_evaluated", "not_classified"]
    run_at: str | None = None


class ErrorResponse(BaseModel):
    error_code: str
    detail: str
