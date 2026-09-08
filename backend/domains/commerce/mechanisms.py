"""The commerce domain's six registered failure mechanisms (hybrid
multi-label attribution — AI_EVALUATION.md SS2). Three deterministic
(recovered from structured telemetry, backend/llm/deterministic_detectors
.py), three semantic (one LLM call per session, backend/llm/prompts/
semantic_attribution.py).

backend.llm.client derives FAILURE_MECHANISMS/DETERMINISTIC_MECHANISMS/
SEMANTIC_MECHANISMS from this registry (same values, same order as
before this module existed) so nothing about current behavior changes —
this is the registry those tuples are now sourced from, not a parallel
second copy of the vocabulary.
"""

from __future__ import annotations

from backend.core.attribution import Mechanism, MechanismRegistry

COMMERCE_MECHANISMS = MechanismRegistry(
    [
        Mechanism(
            "retrieval_failure",
            "deterministic",
            "A recommendation was made but no shown candidate satisfies the user's stated constraints.",
        ),
        Mechanism(
            "poor_ranking",
            "deterministic",
            "The top-ranked recommendation is valid, but a materially higher-rated, also-valid candidate ranks lower.",
        ),
        Mechanism(
            "wrong_tool_selection",
            "deterministic",
            "Two consecutive search actions with no filter/clarify step between them.",
        ),
        Mechanism(
            "unnecessary_clarification",
            "semantic",
            "The agent asks for information the user already sufficiently provided.",
        ),
        Mechanism(
            "wrong_constraint_interpretation",
            "semantic",
            "A compliant candidate existed, but the agent's recommendation violates a stated constraint anyway.",
        ),
        Mechanism(
            "unsupported_product_claim",
            "semantic",
            "The agent asserts a product property unsupported by the product's actual attributes.",
        ),
    ]
)
