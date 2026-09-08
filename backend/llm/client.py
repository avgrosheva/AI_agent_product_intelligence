"""LLM provider abstraction (AI_EVALUATION.md SS3). Two implementations
share this interface: OpenRouterLLMClient (real calls, via an OpenAI-
compatible client pointed at OpenRouter) and RuleBasedMockClient
(deterministic, used in tests/CI and whenever no API key is configured).
Neither implementation, nor SessionContext itself, may ever be constructed
from ground truth — see context_builder.py, which is the single place
session data is assembled from the application database.

Hybrid multi-label attribution redesign: FAILURE_TAXONOMY/FailureClassification
are the OLD exclusive-classifier types, kept only so historical
failure_labels rows and old tests still import successfully — nothing in
the current pipeline produces a FailureClassification anymore.
DETERMINISTIC_MECHANISMS/SEMANTIC_MECHANISMS/MechanismResult/
SemanticAttribution are the current types: one session can independently
have zero, one, or several mechanisms detected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from backend.domains.commerce.mechanisms import COMMERCE_MECHANISMS

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

# The six independently-detected mechanisms (hybrid multi-label
# architecture). "none" and "other" are deliberately absent: none is
# derived (no mechanism fired), and other is deprecated — see
# backend.app.models.enums.FailureMechanism, which this must stay in sync
# with (same six values, same split).
#
# Stage 2 (domain-agnostic core): sourced from the commerce domain's
# registered mechanisms (backend.domains.commerce.mechanisms) — same
# values, same order as when these were hardcoded tuples here, so nothing
# about current behavior changes. A non-shopping domain registers its own
# MechanismRegistry instead; this module (and MechanismResult/
# SemanticAttribution below) would then validate against that domain's
# names instead, unchanged code.
DETERMINISTIC_MECHANISMS = COMMERCE_MECHANISMS.deterministic
SEMANTIC_MECHANISMS = COMMERCE_MECHANISMS.semantic
FAILURE_MECHANISMS = DETERMINISTIC_MECHANISMS + SEMANTIC_MECHANISMS


@dataclass(frozen=True)
class ToolCallSummary:
    tool_name: str
    success: bool
    error_type: str
    result_count: int | None = None


@dataclass(frozen=True)
class ProductEvidence:
    """Observable attributes of one shown/recommended product — the
    minimum needed for the unsupported_product_claim detector to check an
    agent claim against real data. Deliberately excludes margin_pct (and
    any other internal-only business field): everything here is something
    an agent (and therefore a real deployment's classifier) could plausibly
    have seen, never a hidden generator/ground-truth fact."""

    product_id: str
    rank_position: int
    satisfies_constraints: bool
    category: str
    brand: str
    price_rub: int
    ram_gb: int | None
    storage_gb: int | None
    weight_kg: float | None
    cpu_tier: str | None
    gpu_tier: str | None
    screen_in: float | None
    use_case_tags: tuple[str, ...]
    rating: float
    in_stock: bool


@dataclass(frozen=True)
class SessionContext:
    """Everything a detector is allowed to see (Stage 2 review requirement
    #6): transcript, agent actions, tool names/results at a coarse
    abstraction level, constraint-satisfaction signals, and (since the
    hybrid redesign) observable attributes of every shown product. No
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
    recommended_products: tuple[ProductEvidence, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FailureClassification:
    """Deprecated (old exclusive-classifier output) — kept for historical
    failure_labels rows and old tests only. New code should produce
    MechanismResult/SemanticAttribution instead."""

    failure_mode: str
    confidence: float
    evidence_text: str

    def __post_init__(self):
        if self.failure_mode not in FAILURE_TAXONOMY:
            raise ValueError(f"'{self.failure_mode}' is not in the approved taxonomy")


@dataclass(frozen=True)
class MechanismResult:
    """One (mechanism, detected) judgment, from either a deterministic
    detector or an LLM. confidence/evidence_text are None for a
    deterministic detector — a rule doesn't have a confidence score."""

    mechanism: str
    detected: bool
    confidence: float | None
    evidence_text: str | None

    def __post_init__(self):
        if self.mechanism not in FAILURE_MECHANISMS:
            raise ValueError(f"'{self.mechanism}' is not a recognized failure mechanism")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence {self.confidence} outside [0.0, 1.0]")


@dataclass(frozen=True)
class SemanticAttribution:
    """Result of the one semantic LLM call per session: exactly one
    MechanismResult per SEMANTIC_MECHANISMS entry, in that order — any
    subset may be detected=True, independently of the others."""

    results: tuple[MechanismResult, ...]

    def __post_init__(self):
        got = tuple(r.mechanism for r in self.results)
        if got != SEMANTIC_MECHANISMS:
            raise ValueError(f"expected exactly {SEMANTIC_MECHANISMS} in order, got {got}")


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
    """classify_semantic is the current method every real pipeline path
    uses. classify_failure is kept on the protocol only so old callers/tests
    of the exclusive classifier keep working against both implementations;
    it is not invoked anywhere in the current classification_pipeline."""

    def classify_semantic(self, context: SessionContext) -> SemanticAttribution: ...

    def classify_failure(self, context: SessionContext) -> FailureClassification: ...

    def summarize_finding(self, finding: Finding) -> str: ...
