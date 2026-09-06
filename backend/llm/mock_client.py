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

from backend.llm.client import FailureClassification, SessionContext


def _count_action(seq: tuple[str, ...], action_type: str) -> int:
    return sum(1 for a in seq if a == action_type)


def _has_consecutive(seq: tuple[str, ...], action_type: str) -> bool:
    return any(a == action_type and b == action_type for a, b in zip(seq, seq[1:]))


class RuleBasedMockClient:
    """Implements the LLMClient protocol without any network call."""

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
