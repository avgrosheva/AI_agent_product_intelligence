"""Builds SessionContext objects from the application database only.

This is the single chokepoint between the database and every detector
(deterministic or LLM) — every one of them receives its input exclusively
through here, and this module's queries touch only application tables
(sessions, messages, agent_actions, tool_calls, recommendations, products).
It has no code path that opens validation_ground_truth.parquet or
generation_manifest.json, and no query here selects a ground-truth column,
because no such column exists in the application schema (DATA_MODEL.md
SS8). The products join (added for the hybrid multi-label redesign, to
give the unsupported_product_claim detector something to check a claim
against) selects only observable attributes — margin_pct is deliberately
never selected here, since it is internal business data no agent could
plausibly have seen.
"""

from __future__ import annotations

import uuid

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.llm.client import ProductEvidence, SessionContext, ToolCallSummary


def _load_raw_tables(engine: Engine, session_ids: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """session_ids, when given, restricts every query to that set — used
    to build contexts for a bounded evaluation subset (e.g.
    scripts/run_real_llm_evaluation.py) without touching a single row this
    module doesn't already read for the full-dataset path. Still only
    application tables; still no ground-truth reference."""
    ids = [uuid.UUID(s) for s in session_ids] if session_ids is not None else None
    id_filter = " WHERE session_id = ANY(:ids)" if ids is not None else ""
    id_filter_tc = " WHERE tc.session_id = ANY(:ids)" if ids is not None else ""
    params = {"ids": ids} if ids is not None else {}

    with engine.connect() as conn:
        sessions = pd.read_sql(
            text(f"SELECT session_id, num_constraints, requested_category, outcome FROM sessions{id_filter}"),
            conn, params=params,
        )
        messages = pd.read_sql(
            text(
                f"SELECT session_id, turn_index, sender, text FROM messages{id_filter} "
                "ORDER BY session_id, turn_index, sender"
            ),
            conn, params=params,
        )
        actions = pd.read_sql(
            text(
                f"SELECT session_id, sequence_index, action_type FROM agent_actions{id_filter} "
                "ORDER BY session_id, sequence_index"
            ),
            conn, params=params,
        )
        tool_calls = pd.read_sql(
            text(
                f"""
                SELECT tc.session_id, tc.tool_name::text AS tool_name, tc.success, tc.error_type::text AS error_type,
                       (tc.output_json->>'result_count')::int AS result_count
                FROM tool_calls tc{id_filter_tc}
                """
            ),
            conn, params=params,
        )
        recs = pd.read_sql(
            text(
                f"""
                SELECT r.session_id, r.rank_position, r.satisfies_constraints,
                       p.product_id::text AS product_id, p.category::text AS category, p.brand,
                       p.price_rub, p.ram_gb, p.storage_gb, p.weight_kg,
                       p.cpu_tier::text AS cpu_tier, p.gpu_tier::text AS gpu_tier, p.screen_in,
                       p.use_case_tags, p.rating, p.in_stock
                FROM recommendations r
                JOIN products p ON p.product_id = r.product_id
                {id_filter.replace('WHERE session_id', 'WHERE r.session_id')}
                ORDER BY r.session_id, r.rank_position
                """
            ),
            conn, params=params,
        )
    return {"sessions": sessions, "messages": messages, "actions": actions, "tool_calls": tool_calls, "recs": recs}


def build_all_contexts(engine: Engine, session_ids: list[str] | None = None) -> list[SessionContext]:
    """session_ids restricts the result to that subset (order not
    guaranteed to match) — see _load_raw_tables."""
    tables = _load_raw_tables(engine, session_ids)
    sessions = tables["sessions"]
    messages_by_session = {sid: g for sid, g in tables["messages"].groupby("session_id")}
    actions_by_session = {sid: g for sid, g in tables["actions"].groupby("session_id")}
    tools_by_session = {sid: g for sid, g in tables["tool_calls"].groupby("session_id")}
    recs_by_session = {sid: g for sid, g in tables["recs"].groupby("session_id")}

    contexts = []
    for row in sessions.itertuples():
        sid = row.session_id
        msgs = messages_by_session.get(sid)
        transcript = tuple((m.sender, m.text) for m in msgs.itertuples()) if msgs is not None else ()
        acts = actions_by_session.get(sid)
        action_sequence = tuple(acts.action_type) if acts is not None else ()
        tools = tools_by_session.get(sid)
        tool_calls = (
            tuple(
                ToolCallSummary(
                    tool_name=t.tool_name,
                    success=bool(t.success),
                    error_type=t.error_type,
                    result_count=(None if pd.isna(t.result_count) else int(t.result_count)),
                )
                for t in tools.itertuples()
            )
            if tools is not None
            else ()
        )
        recs = recs_by_session.get(sid)
        top_satisfies = None
        any_satisfies = None
        recommended_products: tuple = ()
        if recs is not None and len(recs):
            top_row = recs[recs.rank_position == 1]
            top_satisfies = bool(top_row.iloc[0].satisfies_constraints) if len(top_row) else None
            any_satisfies = bool(recs.satisfies_constraints.any())
            recommended_products = tuple(
                ProductEvidence(
                    product_id=r.product_id,
                    rank_position=int(r.rank_position),
                    satisfies_constraints=bool(r.satisfies_constraints),
                    category=r.category,
                    brand=r.brand,
                    price_rub=int(r.price_rub),
                    ram_gb=(None if pd.isna(r.ram_gb) else int(r.ram_gb)),
                    storage_gb=(None if pd.isna(r.storage_gb) else int(r.storage_gb)),
                    weight_kg=(None if pd.isna(r.weight_kg) else float(r.weight_kg)),
                    cpu_tier=(None if pd.isna(r.cpu_tier) else r.cpu_tier),
                    gpu_tier=(None if pd.isna(r.gpu_tier) else r.gpu_tier),
                    screen_in=(None if pd.isna(r.screen_in) else float(r.screen_in)),
                    use_case_tags=tuple(r.use_case_tags or ()),
                    rating=float(r.rating),
                    in_stock=bool(r.in_stock),
                )
                for r in recs.sort_values("rank_position").itertuples()
            )
        contexts.append(
            SessionContext(
                session_id=sid,
                transcript=transcript,
                action_sequence=action_sequence,
                tool_calls=tool_calls,
                num_constraints=int(row.num_constraints),
                requested_category=row.requested_category,
                top_recommendation_satisfies_constraints=top_satisfies,
                any_shown_recommendation_satisfies_constraints=any_satisfies,
                outcome=row.outcome,
                recommended_products=recommended_products,
            )
        )
    return contexts
