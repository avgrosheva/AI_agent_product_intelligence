"""Builds SessionContext objects from the application database only.

This is the single chokepoint between the database and the classifier —
every classifier implementation receives its input exclusively through
here, and this module's queries touch only application tables (sessions,
messages, agent_actions, tool_calls, recommendations). It has no code path
that opens validation_ground_truth.parquet or generation_manifest.json,
and no query here selects a ground-truth column, because no such column
exists in the application schema (DATA_MODEL.md SS8).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.llm.client import SessionContext, ToolCallSummary


def _load_raw_tables(engine: Engine) -> dict[str, pd.DataFrame]:
    with engine.connect() as conn:
        sessions = pd.read_sql(
            text("SELECT session_id, num_constraints, requested_category, outcome FROM sessions"), conn
        )
        messages = pd.read_sql(
            text("SELECT session_id, turn_index, sender, text FROM messages ORDER BY session_id, turn_index, sender"),
            conn,
        )
        actions = pd.read_sql(
            text("SELECT session_id, sequence_index, action_type FROM agent_actions ORDER BY session_id, sequence_index"),
            conn,
        )
        tool_calls = pd.read_sql(
            text(
                """
                SELECT tc.session_id, tc.tool_name::text AS tool_name, tc.success, tc.error_type::text AS error_type,
                       (tc.output_json->>'result_count')::int AS result_count
                FROM tool_calls tc
                """
            ),
            conn,
        )
        recs = pd.read_sql(
            text(
                """
                SELECT session_id, rank_position, satisfies_constraints
                FROM recommendations
                """
            ),
            conn,
        )
    return {"sessions": sessions, "messages": messages, "actions": actions, "tool_calls": tool_calls, "recs": recs}


def build_all_contexts(engine: Engine) -> list[SessionContext]:
    tables = _load_raw_tables(engine)
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
        if recs is not None and len(recs):
            top_row = recs[recs.rank_position == 1]
            top_satisfies = bool(top_row.iloc[0].satisfies_constraints) if len(top_row) else None
            any_satisfies = bool(recs.satisfies_constraints.any())
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
            )
        )
    return contexts
