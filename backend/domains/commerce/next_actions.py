"""The commerce domain's next-action remediation text, keyed by mechanism
name (and "other"/"none"). backend.investigation.recommend.
synthesize_recommendation's decision logic (ship/hold/roll_back, and
picking the dominant mechanism to explain) is fully generic; this dict is
the domain-specific prose a non-shopping domain would replace with its
own remediation guidance for its own mechanisms."""

from __future__ import annotations

NEXT_ACTION_TEMPLATES: dict[str, str] = {
    "unnecessary_clarification": "Cap or gate clarification when >=3 explicit constraints are already present; re-run offline evaluation; consider a limited rollout.",
    "wrong_constraint_interpretation": "Audit the constraint-parsing logic for the affected segment; add targeted regression tests; re-run offline evaluation before further rollout.",
    "wrong_tool_selection": "Review the tool-selection policy to reduce redundant tool calls in the affected segment; re-run offline evaluation.",
    "retrieval_failure": "Investigate retrieval/catalog coverage for the affected segment; consider expanding fallback ranking logic.",
    "poor_ranking": "Review ranking quality for the affected segment.",
    "unsupported_product_claim": "Audit agent responses in the affected segment for unsupported claims; tighten grounding.",
    "other": "Manually review a sample of sessions in the affected segment to characterize the regression before further rollout.",
    "none": "Manually review a sample of sessions in the affected segment; no single dominant failure mode was identified.",
}
