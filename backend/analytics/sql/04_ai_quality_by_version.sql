-- AI-quality metrics by version. Both eval_types here are computed
-- deterministically by the generator (rule-based, not LLM — AI_EVALUATION.md
-- SS6); answer_faithfulness is excluded because it requires the Stage 3
-- LLM judge and has no rows yet.
SELECT
    s.agent_version,
    count(DISTINCT CASE WHEN e.eval_type = 'offline_task_success' THEN e.session_id END) AS n_sessions_evaluated,
    avg(CASE WHEN e.eval_type = 'offline_task_success' THEN e.score END) AS avg_offline_task_success_score,
    avg(CASE WHEN e.eval_type = 'offline_task_success' AND e.score >= 0.7 THEN 1.0
             WHEN e.eval_type = 'offline_task_success' THEN 0.0 END) AS offline_task_success_rate,
    avg(CASE WHEN e.eval_type = 'constraint_satisfaction' THEN e.score END) AS avg_constraint_satisfaction_score
FROM sessions s
JOIN evaluations e ON e.session_id = s.session_id
GROUP BY s.agent_version
ORDER BY s.agent_version;
