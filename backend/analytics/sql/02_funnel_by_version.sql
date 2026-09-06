-- Funnel step-through (impression -> click -> add_to_cart -> purchase).
-- Demonstrates: CTE + conditional aggregation to collapse an event log to
-- one row per session before computing step-through rates.
WITH session_funnel AS (
    SELECT
        s.session_id,
        s.agent_version,
        max(CASE WHEN pe.event_type = 'impression' THEN 1 ELSE 0 END) AS had_impression,
        max(CASE WHEN pe.event_type = 'click' THEN 1 ELSE 0 END) AS had_click,
        max(CASE WHEN pe.event_type = 'add_to_cart' THEN 1 ELSE 0 END) AS had_cart,
        max(CASE WHEN pe.event_type = 'purchase' THEN 1 ELSE 0 END) AS had_purchase
    FROM sessions s
    LEFT JOIN product_events pe ON pe.session_id = s.session_id
    GROUP BY s.session_id, s.agent_version
)
SELECT
    agent_version,
    count(*) AS n_sessions,
    sum(had_impression) AS n_impression,
    sum(had_click) AS n_click,
    sum(had_cart) AS n_cart,
    sum(had_purchase) AS n_purchase,
    sum(had_click)::numeric / NULLIF(sum(had_impression), 0) AS impression_to_click_rate,
    sum(had_cart)::numeric / NULLIF(sum(had_click), 0) AS click_to_cart_rate,
    sum(had_purchase)::numeric / NULLIF(sum(had_cart), 0) AS cart_to_purchase_rate
FROM session_funnel
GROUP BY agent_version
ORDER BY agent_version;
