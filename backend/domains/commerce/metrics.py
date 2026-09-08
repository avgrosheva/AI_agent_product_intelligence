"""The commerce domain's metric-name -> session-level-column bindings.
backend.analytics.experiment_results.analyze_metric is the generic
mechanism (look up a metric's value column + eligibility filter, compute
per-version means and the cluster-level significance test); this dict is
the domain-specific data a non-shopping domain would replace to bind its
own metric names to its own session-level columns (which would come from
that domain's own base query, not session_level_base.sql — see that
file's header for the remaining commerce-specific coupling this stage
does not remove).

Moved here unchanged from backend.analytics.experiment_results, which
re-exports this exact object under the same name so existing imports
(`from backend.analytics.experiment_results import METRIC_VALUE_COLUMNS`)
keep working.
"""

from __future__ import annotations

# metric_name -> (value_column, eligibility_mask_fn | None)
# eligibility_mask_fn(df) -> boolean Series; None means "all rows".
METRIC_VALUE_COLUMNS: dict[str, tuple[str, object]] = {
    "conversion_rate": ("converted", None),
    "add_to_cart_rate": ("added_to_cart", None),
    "abandonment_rate": ("abandoned", None),
    "impression_to_click_rate": ("had_click", lambda df: df.had_impression == 1),
    "click_to_cart_rate": ("had_cart", lambda df: df.had_click == 1),
    "cart_to_purchase_rate": ("had_purchase", lambda df: df.had_cart == 1),
    "time_to_first_recommendation_ms": ("time_to_first_recommendation_ms", lambda df: df.time_to_first_recommendation_ms.notna()),
    "time_to_goal_seconds": ("time_to_goal_seconds", lambda df: df.time_to_goal_seconds.notna()),
    "turns_per_session": ("num_turns", None),
    "clarification_rate": ("has_clarify", None),
    "unnecessary_clarification_rate": ("has_clarify", lambda df: df.num_constraints >= 3),
    "tool_calls_per_session": ("n_tool_calls", None),
    "tool_success_rate": ("tool_success_rate_session", lambda df: df.tool_success_rate_session.notna()),
    "tool_error_rate": ("tool_error_rate_session", lambda df: df.tool_error_rate_session.notna()),
    "dead_end_rate": ("is_dead_end", None),
    "action_sequence_length": ("n_actions", None),
    "offline_task_success_rate": ("offline_task_success_ge_0_7", lambda df: df.offline_task_success_score.notna()),
    "constraint_satisfaction_rate": ("constraint_satisfaction_score", lambda df: df.constraint_satisfaction_score.notna()),
    "cost_per_session_usd": ("total_cost_usd", None),
    "revenue_per_session_usd": ("revenue_usd", None),
    "gross_margin_proxy_usd": ("margin_proxy_usd", None),
}
