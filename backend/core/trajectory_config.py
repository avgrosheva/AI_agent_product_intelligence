"""Stage 5 task 5: which action-type/outcome literals
backend.investigation.trajectory_attribution looks for are domain data,
not hardcoded — so a non-commerce domain that DOES register mechanisms
(unlike support, which registers none and never reaches this code path)
could reuse the exact same trajectory-reconstruction/association-testing
mechanism with its own vocabulary instead of commerce's
clarify/search/abandon_flow/converted.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrajectoryConfig:
    # Which analytics_base_df column carries the categorical outcome, and
    # which of its values marks the negative terminal outcome trajectory
    # associations are tested against sessions that did NOT reach (see
    # backend.investigation.pipeline.run_investigation).
    outcome_column: str = "outcome"
    negative_outcome_value: str = "abandoned"
    # Which 0/1 column trajectory-pattern association is tested against
    # (must be the "reached an answer" population's binary outcome).
    positive_outcome_column: str = "converted"
    # Action-type literals canonicalize_patterns()/_structural_features()
    # look for when collapsing a rare exact sequence to a structural key.
    clarify_action: str = "clarify"
    repeat_action: str = "search"
    terminal_negative_action: str = "abandon_flow"
