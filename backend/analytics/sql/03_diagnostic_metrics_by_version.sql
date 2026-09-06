-- Agent-behavior diagnostics (post_treatment_mechanism metrics, METRICS.md SS3).
-- Demonstrates: window-function-style ordered aggregation (array_agg ...
-- ORDER BY) to reconstruct each session's trajectory, array containment
-- to detect specific patterns, and FILTER (WHERE ...) for a conditional rate.
WITH trajectories AS (
    SELECT
        session_id,
        array_agg(action_type::text ORDER BY sequence_index) AS action_sequence,
        count(*) AS n_actions
    FROM agent_actions
    GROUP BY session_id
),
session_diag AS (
    SELECT
        s.session_id,
        s.agent_version,
        s.num_constraints,
        t.n_actions,
        (t.action_sequence @> ARRAY['clarify']::text[]) AS has_clarify,
        (t.action_sequence = ARRAY['understand_query', 'search', 'search', 'search', 'abandon_flow']::text[]) AS is_dead_end,
        (SELECT count(*) FROM tool_calls tc WHERE tc.session_id = s.session_id) AS n_tool_calls,
        (SELECT avg(CASE WHEN tc.success THEN 1.0 ELSE 0.0 END) FROM tool_calls tc WHERE tc.session_id = s.session_id) AS tool_success_rate_session
    FROM sessions s
    JOIN trajectories t ON t.session_id = s.session_id
)
SELECT
    agent_version,
    count(*) AS n_sessions,
    avg(CASE WHEN has_clarify THEN 1.0 ELSE 0.0 END) AS clarification_rate,
    avg(CASE WHEN has_clarify THEN 1.0 ELSE 0.0 END) FILTER (WHERE num_constraints >= 3) AS unnecessary_clarification_rate,
    count(*) FILTER (WHERE num_constraints >= 3) AS n_sessions_3plus_constraints,
    avg(n_tool_calls) AS avg_tool_calls_per_session,
    avg(tool_success_rate_session) AS avg_tool_success_rate,
    avg(CASE WHEN is_dead_end THEN 1.0 ELSE 0.0 END) AS dead_end_rate,
    avg(n_actions) AS avg_action_sequence_length
FROM session_diag
GROUP BY agent_version
ORDER BY agent_version;
