-- Shared session-level base table used by experiment_results.py to feed the
-- per-user cluster-level inferential layer. Not one of the 8 numbered
-- "representative analyses" — this is the infrastructure query every
-- metric's cluster reduction starts from, one row per session.
WITH trajectories AS (
    SELECT
        session_id,
        array_agg(action_type::text ORDER BY sequence_index) AS action_sequence,
        count(*) AS n_actions
    FROM agent_actions
    GROUP BY session_id
),
consecutive_search AS (
    -- STAGE 2 DESCRIPTIVE SANITY CHECK ONLY (backend/analytics/effects_verification.py's
    -- tool_selection_v2_improved check). Precisely isolates one known
    -- template's signature (two `search` actions back to back, no
    -- `clarify` between them) as a one-off pattern match at the same
    -- specificity level as dead_end_rate below — NOT a general
    -- trajectory-pattern analyzer.
    --
    -- Stage 3's trajectory analysis (INVESTIGATION.md SS5) MUST NOT read
    -- has_consecutive_search or treat it as a privileged shortcut to "the"
    -- planted answer. It has to derive its own trajectory patterns from
    -- agent_actions independently and evaluate their association with
    -- outcomes on their own terms — this column exists only to sanity-check
    -- one specific Stage 2 metric proxy, not to seed or shortcut Stage 3.
    SELECT DISTINCT session_id
    FROM (
        SELECT
            session_id,
            action_type,
            lead(action_type) OVER (PARTITION BY session_id ORDER BY sequence_index) AS next_action_type
        FROM agent_actions
    ) pairs
    WHERE action_type = 'search' AND next_action_type = 'search'
),
tool_agg AS (
    SELECT
        session_id,
        count(*) AS n_tool_calls,
        count(*) FILTER (WHERE tool_name = 'search_products') AS n_search_calls,
        avg(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS tool_success_rate_session,
        avg(CASE WHEN NOT success THEN 1.0 ELSE 0.0 END) AS tool_error_rate_session
    FROM tool_calls
    GROUP BY session_id
),
funnel AS (
    SELECT
        session_id,
        max(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END) AS had_impression,
        max(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) AS had_click,
        max(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END) AS had_cart,
        max(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS had_purchase
    FROM product_events
    GROUP BY session_id
),
revenue AS (
    SELECT
        pe.session_id,
        coalesce(sum(pe.price_at_event) FILTER (WHERE pe.event_type = 'purchase'), 0) / 95.0 AS revenue_usd,
        coalesce(sum(pe.price_at_event * p.margin_pct) FILTER (WHERE pe.event_type = 'purchase'), 0) / 95.0 AS gross_margin_component_usd
    FROM product_events pe
    JOIN products p ON p.product_id = pe.product_id
    GROUP BY pe.session_id
),
evals AS (
    SELECT
        session_id,
        max(score) FILTER (WHERE eval_type = 'offline_task_success') AS offline_task_success_score,
        max(score) FILTER (WHERE eval_type = 'constraint_satisfaction') AS constraint_satisfaction_score
    FROM evaluations
    GROUP BY session_id
),
first_rec AS (
    SELECT session_id, min(shown_at) AS first_shown_at
    FROM recommendations
    GROUP BY session_id
),
purchase_time AS (
    SELECT session_id, min(event_time) AS purchase_at
    FROM product_events
    WHERE event_type = 'purchase'
    GROUP BY session_id
)
SELECT
    s.session_id,
    s.user_id,
    s.experiment_id,
    s.agent_version,
    s.requested_category,
    s.platform,
    s.device_tier,
    s.locale,
    u.persona,
    s.num_constraints,
    CASE WHEN s.num_constraints <= 1 THEN '0-1' WHEN s.num_constraints = 2 THEN '2' ELSE '3+' END AS constraint_count_bucket,
    s.outcome,
    s.num_turns,
    s.total_latency_ms,
    s.total_cost_usd::float8 AS total_cost_usd,
    s.started_at,
    (s.outcome = 'purchase')::int AS converted,
    (s.outcome IN ('purchase', 'add_to_cart_only'))::int AS added_to_cart,
    (s.outcome = 'abandoned')::int AS abandoned,
    coalesce(f.had_impression, 0) AS had_impression,
    coalesce(f.had_click, 0) AS had_click,
    coalesce(f.had_cart, 0) AS had_cart,
    coalesce(f.had_purchase, 0) AS had_purchase,
    (t.action_sequence @> ARRAY['clarify']::text[])::int AS has_clarify,
    (t.action_sequence = ARRAY['understand_query', 'search', 'search', 'search', 'abandon_flow']::text[])::int AS is_dead_end,
    (cs.session_id IS NOT NULL)::int AS has_consecutive_search,
    t.n_actions,
    coalesce(ta.n_tool_calls, 0) AS n_tool_calls,
    coalesce(ta.n_search_calls, 0) AS n_search_calls,
    ta.tool_success_rate_session,
    ta.tool_error_rate_session,
    e.offline_task_success_score,
    (e.offline_task_success_score >= 0.7)::int AS offline_task_success_ge_0_7,
    e.constraint_satisfaction_score,
    coalesce(r.revenue_usd, 0) AS revenue_usd,
    coalesce(r.gross_margin_component_usd, 0) - s.total_cost_usd::float8 AS margin_proxy_usd,
    EXTRACT(EPOCH FROM (fr.first_shown_at - s.started_at)) * 1000 AS time_to_first_recommendation_ms,
    CASE
        WHEN s.outcome = 'purchase' THEN EXTRACT(EPOCH FROM (pt.purchase_at - s.started_at))
        WHEN s.outcome = 'abandoned' THEN EXTRACT(EPOCH FROM (s.ended_at - s.started_at))
    END AS time_to_goal_seconds
FROM sessions s
JOIN users u ON u.user_id = s.user_id
JOIN trajectories t ON t.session_id = s.session_id
LEFT JOIN consecutive_search cs ON cs.session_id = s.session_id
LEFT JOIN tool_agg ta ON ta.session_id = s.session_id
LEFT JOIN funnel f ON f.session_id = s.session_id
LEFT JOIN revenue r ON r.session_id = s.session_id
LEFT JOIN evals e ON e.session_id = s.session_id
LEFT JOIN first_rec fr ON fr.session_id = s.session_id
LEFT JOIN purchase_time pt ON pt.session_id = s.session_id;
