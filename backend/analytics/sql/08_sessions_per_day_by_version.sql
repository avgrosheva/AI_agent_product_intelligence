-- Time-series example: daily session volume and conversion by arm, with a
-- 7-day trailing rolling average (window function with an explicit frame).
WITH daily AS (
    SELECT
        date_trunc('day', started_at)::date AS day,
        agent_version,
        count(*) AS n_sessions,
        avg(CASE WHEN outcome = 'purchase' THEN 1.0 ELSE 0.0 END) AS daily_conversion_rate
    FROM sessions
    GROUP BY 1, 2
)
SELECT
    day,
    agent_version,
    n_sessions,
    daily_conversion_rate,
    avg(daily_conversion_rate) OVER (
        PARTITION BY agent_version ORDER BY day
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS conversion_rate_7d_rolling_avg
FROM daily
ORDER BY agent_version, day;
