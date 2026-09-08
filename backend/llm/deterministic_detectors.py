"""Deterministic failure detectors (hybrid multi-label attribution
redesign, AI_EVALUATION.md SS3 addendum).

Each detector is a pure function of a SessionContext: no LLM call, no
randomness, no ground truth. Each returns a MechanismResult with
confidence=None and evidence_text=None — a deterministic rule doesn't have
a confidence score, and its "evidence" is the rule itself, not a
generated sentence (the caller can still explain a detection by showing
the observable fields that triggered it, but that's presentation, not
part of this module's contract).

Scope, stated plainly rather than fabricated coverage:
- retrieval_failure and poor_ranking are checked against every shown
  recommendation this detector can see (SessionContext.recommended_products)
  — up to 5 candidates, matching what the generator ever shows. A
  narrower catalog than what a real deployment might show could reduce
  recall; that's a property of the input, not this module.
- wrong_tool_selection here catches exactly one concrete, observable
  pattern: two consecutive `search` actions with no `filter`/`clarify` step
  between them. Other product/agent-level notions of "wrong tool
  selection" (e.g. calling a detail/compare tool before any retrieval at
  all) are NOT implemented, because SessionContext's action_sequence does
  not currently distinguish a detail/compare tool call from a generic
  `answer` action clearly enough to detect it without guessing — this
  detector is intentionally narrow rather than fabricated.
"""

from __future__ import annotations

from backend.llm.client import MechanismResult, SessionContext

# Same threshold the generator itself uses to decide whether a
# rating difference between two constraint-satisfying candidates counts as
# "materially better" (datagen/session_builder.py POOR_RANKING_MIN_RATING_GAP)
# — not tuned against ground truth, tuned against the catalog's own rating
# distribution before any detector evaluation was run.
POOR_RANKING_MIN_RATING_GAP = 0.15

DETECTOR_VERSION = "deterministic_detectors_v1"


def detect_retrieval_failure(context: SessionContext) -> MechanismResult:
    """True when a recommendation was made but not one shown candidate
    satisfies the user's stated constraints — the observable signature of
    "no matching product could be found," not of a bad final pick when
    matches existed (see detect_poor_ranking / semantic wrong_constraint
    detector for those cases, which require at least one compliant shown
    candidate)."""
    products = context.recommended_products
    if not products:
        return MechanismResult("retrieval_failure", False, None, None)
    if any(p.satisfies_constraints for p in products):
        return MechanismResult("retrieval_failure", False, None, None)
    return MechanismResult(
        "retrieval_failure",
        True,
        None,
        f"None of the {len(products)} shown candidates satisfy the user's stated constraints.",
    )


def detect_poor_ranking(context: SessionContext, min_rating_gap: float = POOR_RANKING_MIN_RATING_GAP) -> MechanismResult:
    """True when the top-ranked recommendation is itself valid (satisfies
    every stated constraint) but a lower-ranked candidate that ALSO
    satisfies every stated constraint has a materially higher rating.
    Never fires when the top pick violates a constraint — that is a
    constraint-interpretation problem, not a ranking-quality one."""
    products = context.recommended_products
    if not products or not context.top_recommendation_satisfies_constraints:
        return MechanismResult("poor_ranking", False, None, None)
    top = products[0]
    better = [p for p in products[1:] if p.satisfies_constraints and (p.rating - top.rating) >= min_rating_gap]
    if not better:
        return MechanismResult("poor_ranking", False, None, None)
    best = max(better, key=lambda p: p.rating)
    return MechanismResult(
        "poor_ranking",
        True,
        None,
        f"Rank {best.rank_position} candidate (rating {best.rating}) satisfies every stated constraint and "
        f"rates materially higher than the top-ranked pick (rating {top.rating}), which also satisfies them.",
    )


def detect_wrong_tool_selection(context: SessionContext) -> MechanismResult:
    """True on two consecutive `search` actions with nothing (no filter,
    no clarify, no recommend) between them — a redundant re-search with no
    new information, independent of whether the session ultimately
    succeeded or abandoned."""
    seq = context.action_sequence
    for i in range(len(seq) - 1):
        if seq[i] == "search" and seq[i + 1] == "search":
            return MechanismResult(
                "wrong_tool_selection",
                True,
                None,
                f"Two consecutive 'search' actions (positions {i}, {i + 1}) with no filter/clarify step between them.",
            )
    return MechanismResult("wrong_tool_selection", False, None, None)


def run_deterministic_detectors(context: SessionContext) -> tuple[MechanismResult, ...]:
    return (
        detect_retrieval_failure(context),
        detect_poor_ranking(context),
        detect_wrong_tool_selection(context),
    )
