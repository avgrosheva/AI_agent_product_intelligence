-- Economic metrics by version (METRICS.md SS6).
-- Demonstrates: multiple CTEs, an explicit ratio-of-sums metric
-- (cost_per_successful_task, NOT a per-session average), and a fixed,
-- documented currency-conversion constant so cost (stored in USD) and
-- revenue/margin (derived from RUB product prices) can be compared.
--
-- USD_TO_RUB = 95.0 is an illustrative constant for this portfolio project,
-- not a live/real exchange rate; it is applied identically to both arms so
-- it cancels out of any v1-vs-v2 comparison and only affects the absolute
-- USD-denominated numbers shown in the report.
WITH revenue AS (
    SELECT
        s.agent_version,
        s.session_id,
        s.total_cost_usd,
        coalesce(sum(pe.price_at_event) FILTER (WHERE pe.event_type = 'purchase'), 0) AS session_revenue_rub,
        coalesce(sum(pe.price_at_event * p.margin_pct) FILTER (WHERE pe.event_type = 'purchase'), 0) AS session_margin_rub
    FROM sessions s
    LEFT JOIN product_events pe ON pe.session_id = s.session_id
    LEFT JOIN products p ON p.product_id = pe.product_id
    GROUP BY s.agent_version, s.session_id, s.total_cost_usd
)
SELECT
    agent_version,
    count(*) AS n_sessions,
    avg(total_cost_usd) AS avg_cost_per_session_usd,
    avg(session_revenue_rub) / 95.0 AS avg_revenue_per_session_usd,
    sum(total_cost_usd) / NULLIF(count(*) FILTER (WHERE session_revenue_rub > 0), 0) AS cost_per_successful_task_usd,
    avg(session_margin_rub / 95.0 - total_cost_usd) AS avg_margin_proxy_usd,
    (sum(total_cost_usd) * 95.0) / NULLIF(sum(session_revenue_rub), 0) AS cost_to_serve_ratio
FROM revenue
GROUP BY agent_version
ORDER BY agent_version;
