"""Deterministic rule-based classifier (AI_EVALUATION.md SS3).

Used as the CI/test fallback and as the default classification path when
no LLM API key is configured. Operates only on `SessionContext` — the same
observable-only input the real Anthropic client receives — so its
evaluation against ground truth (scripts/evaluate_classifier.py) is a fair
comparison of "what can be inferred from observable signals alone," not a
lookup. Its heuristics were designed from the taxonomy definitions in
AI_EVALUATION.md, not by reading validation_ground_truth.parquet.
"""

from __future__ import annotations

from backend.llm.client import FailureClassification, MechanismResult, SemanticAttribution, SessionContext

# Substring an agent message would use to state a use-case claim, matching
# datagen's render_unsupported_claim_sentence templates ("great for
# gaming", "well-suited for content creation", etc.) — observable text
# matching, not a read of any hidden generator flag.
_USE_CASE_PHRASES = {
    "programming": "programming",
    "gaming": "gaming",
    "office": "office",
    "content_creation": "content creation",
}


def _count_action(seq: tuple[str, ...], action_type: str) -> int:
    return sum(1 for a in seq if a == action_type)


def _has_consecutive(seq: tuple[str, ...], action_type: str) -> bool:
    return any(a == action_type and b == action_type for a, b in zip(seq, seq[1:]))


class RuleBasedMockClient:
    """Implements the LLMClient protocol without any network call.

    classify_semantic is the current method, and covers only the three
    SEMANTIC mechanisms (unnecessary_clarification,
    wrong_constraint_interpretation, unsupported_product_claim) — the
    three deterministic mechanisms (retrieval_failure, poor_ranking,
    wrong_tool_selection) are never guessed by any LLM or mock, real or
    fake; see backend.llm.deterministic_detectors, which both the real and
    mock pipelines call for those. classify_failure (below) is the old
    exclusive-classifier method, kept only for historical compatibility."""

    def classify_semantic(self, context: SessionContext) -> SemanticAttribution:
        results: list[MechanismResult] = []

        has_clarify = "clarify" in context.action_sequence
        if has_clarify and context.num_constraints >= 3:
            confidence = 0.90 if context.num_constraints >= 4 else 0.78
            results.append(
                MechanismResult(
                    "unnecessary_clarification",
                    True,
                    confidence,
                    f"agent asked a clarifying question despite {context.num_constraints} stated constraints",
                )
            )
        else:
            results.append(
                MechanismResult("unnecessary_clarification", False, 0.85, "no excess clarification observed")
            )

        if (
            context.top_recommendation_satisfies_constraints is False
            and context.num_constraints >= 1
            and context.any_shown_recommendation_satisfies_constraints
        ):
            results.append(
                MechanismResult(
                    "wrong_constraint_interpretation",
                    True,
                    0.72,
                    f"top recommendation did not satisfy all {context.num_constraints} stated constraints "
                    f"for {context.requested_category}, even though another shown option did",
                )
            )
        else:
            results.append(
                MechanismResult(
                    "wrong_constraint_interpretation",
                    False,
                    0.80,
                    "no constraint violation observed among a set that includes a compliant candidate",
                )
            )

        top = context.recommended_products[0] if context.recommended_products else None
        claim_detected = False
        claim_evidence = "no product-attribute claim observed in the transcript"
        if top is not None:
            agent_texts = [text.lower() for sender, text in context.transcript if sender == "agent"]
            for tag, phrase in _USE_CASE_PHRASES.items():
                if tag in top.use_case_tags:
                    continue
                if any(phrase in text for text in agent_texts):
                    claim_detected = True
                    claim_evidence = (
                        f"agent message references '{phrase}' but the recommended product's use_case_tags "
                        f"do not include '{tag}'"
                    )
                    break
        results.append(
            MechanismResult(
                "unsupported_product_claim", claim_detected, 0.70 if claim_detected else 0.75, claim_evidence
            )
        )

        return SemanticAttribution(results=tuple(results))

    def classify_failure(self, context: SessionContext) -> FailureClassification:
        candidates: list[FailureClassification] = []

        has_clarify = "clarify" in context.action_sequence
        if has_clarify and context.num_constraints >= 3:
            confidence = 0.90 if context.num_constraints >= 4 else 0.78
            candidates.append(
                FailureClassification(
                    failure_mode="unnecessary_clarification",
                    confidence=confidence,
                    evidence_text=f"agent asked a clarifying question despite {context.num_constraints} stated constraints",
                )
            )

        if context.top_recommendation_satisfies_constraints is False and context.num_constraints >= 1:
            # Distinguish "a good match existed but wasn't chosen/ranked first"
            # (wrong_constraint_interpretation) from "nothing shown satisfied
            # the constraints at all" (retrieval_failure) using only what was
            # actually shown to the user — both are observable, neither reads
            # ground truth.
            if context.any_shown_recommendation_satisfies_constraints:
                candidates.append(
                    FailureClassification(
                        failure_mode="wrong_constraint_interpretation",
                        confidence=0.72,
                        evidence_text=(
                            f"top recommendation did not satisfy all {context.num_constraints} stated constraints "
                            f"for {context.requested_category}, even though another shown option did"
                        ),
                    )
                )
            else:
                candidates.append(
                    FailureClassification(
                        failure_mode="retrieval_failure",
                        confidence=0.68,
                        evidence_text=(
                            f"none of the shown recommendations satisfied all {context.num_constraints} "
                            f"stated constraints for {context.requested_category}"
                        ),
                    )
                )

        n_search = _count_action(context.action_sequence, "search")
        ends_in_abandon = bool(context.action_sequence) and context.action_sequence[-1] == "abandon_flow"
        if n_search >= 2 and _has_consecutive(context.action_sequence, "search") and not ends_in_abandon:
            # A session that gives up after repeated searching (ends in
            # abandon_flow) is a distinct, dead-end pattern, not the same
            # observable signature as redundant-but-eventually-successful
            # tool use — both are "2+ consecutive searches," but only the
            # latter is what wrong_tool_selection actually describes.
            confidence = 0.65 if n_search == 2 else 0.80
            candidates.append(
                FailureClassification(
                    failure_mode="wrong_tool_selection",
                    confidence=confidence,
                    evidence_text=f"{n_search} search_products calls back-to-back with no intervening clarification, session still reached an answer",
                )
            )

        no_recommendation = context.top_recommendation_satisfies_constraints is None
        reached_recommend = "recommend" in context.action_sequence
        empty_tool_results = any(
            tc.error_type == "empty_result" or (tc.result_count is not None and tc.result_count == 0)
            for tc in context.tool_calls
        )
        if no_recommendation and not reached_recommend and empty_tool_results:
            candidates.append(
                FailureClassification(
                    failure_mode="retrieval_failure",
                    confidence=0.75,
                    evidence_text="session ended without a recommendation and at least one tool call returned an empty result",
                )
            )

        if not candidates:
            return FailureClassification(
                failure_mode="none",
                confidence=0.92,
                evidence_text="no observable failure pattern matched (no excess clarification, constraints satisfied or none stated, no redundant search, retrieval succeeded)",
            )

        return max(candidates, key=lambda c: c.confidence)

    def summarize_finding(self, finding) -> str:
        return (
            f"In segment '{finding.segment_label}', {finding.metric_name} moved from "
            f"{finding.v1_value:.3f} (v1) to {finding.v2_value:.3f} (v2) (p={finding.p_value:.4f}). "
            f"The dominant associated failure mode is '{finding.dominant_failure_mode}'."
        )
