-- Guardrail metrics by version (METRICS.md SS5).
-- Demonstrates: percentile_cont (ordered-set aggregate) for latency
-- percentiles, and a correlated scalar subquery for the tool error rate.
SELECT
    s.agent_version,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY s.total_latency_ms) AS median_latency_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY s.total_latency_ms) AS p95_latency_ms,
    avg(s.total_latency_ms) AS avg_latency_ms,
    avg(s.total_cost_usd) AS avg_cost_per_session_usd,
    (
        SELECT avg(CASE WHEN NOT tc.success THEN 1.0 ELSE 0.0 END)
        FROM tool_calls tc
        JOIN sessions s2 ON s2.session_id = tc.session_id
        WHERE s2.agent_version = s.agent_version
    ) AS tool_error_rate
FROM sessions s
GROUP BY s.agent_version
ORDER BY s.agent_version;
