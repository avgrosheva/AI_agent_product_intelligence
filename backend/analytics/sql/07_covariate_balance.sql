-- Pre-treatment covariate balance by arm (Stage 1 review requirement #4).
-- Demonstrates: UNION ALL to tidy several dimensions into one table, and a
-- window function (SUM() OVER PARTITION BY) to get within-arm percentages
-- without a second aggregation pass.
--
-- All six dimensions here are pre-treatment (METRICS.md SS7): fixed at
-- session intake (or, for persona/locale, fixed per user) before the agent
-- acts, so none of them should differ systematically between arms under
-- correct randomization. This query itself is purely descriptive (counts
-- and within-arm percentages, no significance test) for every dimension.
-- backend/analytics/balance.py adds a standardized-mean-difference (SMD)
-- summary for the four session-varying dimensions here (requested_category,
-- constraint_count_bucket, platform, device_tier) — deliberately NOT a
-- session-level chi-square test, since the experiment randomizes users,
-- not sessions, and a pooled-session test would treat correlated sessions
-- as independent. For persona/locale (fixed per user), balance.py runs a
-- proper chi-square at the user level, where each row is independent. See
-- backend/analytics/balance.py's module docstring for the full rationale
-- and the explicit no-rebalancing policy.
WITH session_scope AS (
    SELECT
        s.session_id,
        s.agent_version,
        s.requested_category,
        s.platform,
        s.device_tier,
        s.locale,
        u.persona,
        CASE
            WHEN s.num_constraints <= 1 THEN '0-1'
            WHEN s.num_constraints = 2 THEN '2'
            ELSE '3+'
        END AS constraint_count_bucket
    FROM sessions s
    JOIN users u ON u.user_id = s.user_id
),
per_dimension AS (
    SELECT 'requested_category' AS dimension, requested_category::text AS value, agent_version, count(*) AS n
    FROM session_scope GROUP BY 1, 2, 3
    UNION ALL
    SELECT 'constraint_count_bucket', constraint_count_bucket, agent_version, count(*)
    FROM session_scope GROUP BY 1, 2, 3
    UNION ALL
    SELECT 'platform', platform::text, agent_version, count(*)
    FROM session_scope GROUP BY 1, 2, 3
    UNION ALL
    SELECT 'device_tier', device_tier::text, agent_version, count(*)
    FROM session_scope GROUP BY 1, 2, 3
    UNION ALL
    SELECT 'locale', locale::text, agent_version, count(*)
    FROM session_scope GROUP BY 1, 2, 3
    UNION ALL
    SELECT 'persona', persona::text, agent_version, count(*)
    FROM session_scope GROUP BY 1, 2, 3
)
SELECT
    dimension,
    value,
    agent_version,
    n,
    n::numeric / sum(n) OVER (PARTITION BY dimension, agent_version) AS pct_within_arm
FROM per_dimension
ORDER BY dimension, value, agent_version;
