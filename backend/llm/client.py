"""LLM provider abstraction (AI_EVALUATION.md SS3). Two implementations
share this interface: AnthropicLLMClient (real calls) and
RuleBasedMockClient (deterministic, used in tests/CI and whenever no API
key is configured). Neither implementation, nor SessionContext itself, may
ever be constructed from ground truth — see context_builder.py, which is
the single place session data is assembled from the application database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

FAILURE_TAXONOMY = (
    "unnecessary_clarification",
    "wrong_constraint_interpretation",
    "poor_ranking",
    "wrong_tool_selection",
    "unsupported_product_claim",
    "retrieval_failure",
    "other",
    "none",
)


@dataclass(frozen=True)
class ToolCallSummary:
    tool_name: str
    success: bool
    error_type: str
    result_count: int | None = None


@dataclass(frozen=True)
class SessionContext:
    """Everything the classifier is allowed to see (Stage 2 review
    requirement #6): transcript, agent actions, tool names/results at a
    coarse abstraction level, and constraint-satisfaction signals. No
    ground-truth field exists on this class, structurally — there is
    nothing here a session-scoped instance of it *could* leak, even by a
    future coding mistake elsewhere in this module.
    """

    session_id: str
    transcript: tuple[tuple[str, str], ...]          # ((sender, text), ...) ordered
    action_sequence: tuple[str, ...]                  # action_type values, ordered
    tool_calls: tuple[ToolCallSummary, ...]
    num_constraints: int
    requested_category: str
    top_recommendation_satisfies_constraints: bool | None
    any_shown_recommendation_satisfies_constraints: bool | None
    outcome: str


@dataclass(frozen=True)
class FailureClassification:
    failure_mode: str
    confidence: float
    evidence_text: str

    def __post_init__(self):
        if self.failure_mode not in FAILURE_TAXONOMY:
            raise ValueError(f"'{self.failure_mode}' is not in the approved taxonomy")


@dataclass(frozen=True)
class Finding:
    """Minimal structured payload passed to summarize_finding — every
    number is already computed deterministically; the LLM may only
    rephrase, never invent or recompute (AI_EVALUATION.md SS7)."""

    segment_label: str
    metric_name: str
    v1_value: float
    v2_value: float
    p_value: float
    excess_contribution: float
    dominant_failure_mode: str
    share_of_excess_abandonment: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


class LLMClient(Protocol):
    def classify_failure(self, context: SessionContext) -> FailureClassification: ...

    def summarize_finding(self, finding: Finding) -> str: ...
