-- Descriptive (session-level) core product metrics by experiment arm.
-- Demonstrates: conditional aggregation (CASE WHEN inside AVG).
-- These are display/descriptive numbers only (METRICS.md); the
-- significance verdict for each is computed separately at the per-user
-- cluster level (backend/analytics/experiment_results.py).
SELECT
    agent_version,
    count(*) AS n_sessions,
    count(DISTINCT user_id) AS n_users,
    avg(CASE WHEN outcome = 'purchase' THEN 1.0 ELSE 0.0 END) AS conversion_rate,
    avg(CASE WHEN outcome IN ('purchase', 'add_to_cart_only') THEN 1.0 ELSE 0.0 END) AS add_to_cart_rate,
    avg(CASE WHEN outcome = 'abandoned' THEN 1.0 ELSE 0.0 END) AS abandonment_rate,
    avg(CASE WHEN outcome = 'no_action' THEN 1.0 ELSE 0.0 END) AS no_action_rate,
    avg(num_turns) AS avg_turns_per_session,
    avg(total_latency_ms) AS avg_latency_ms,
    avg(total_cost_usd) AS avg_cost_usd
FROM sessions
GROUP BY agent_version
ORDER BY agent_version;
