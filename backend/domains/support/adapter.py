"""SupportAdapter: the support domain's DomainAdapter implementation
(Stage 3 task 6's proof fixture). Reads exclusively from the generic
ingestion tables (backend.ingestion.models) — never products/
recommendations/product_events, and never any commerce ORM model."""

from __future__ import annotations

import uuid

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.core.attribution import MechanismRegistry
from backend.core.guardrails import GuardrailDefinition
from backend.core.metrics import MetricDefinition
from backend.core.session import GenericSessionContext, GenericToolCall
from backend.domains.support.guardrails import SUPPORT_GUARDRAILS
from backend.domains.support.mechanisms import SUPPORT_MECHANISMS
from backend.domains.support.metrics import SUPPORT_METRIC_REGISTRY, SUPPORT_METRIC_VALUE_COLUMNS

DOMAIN = "support"


class SupportAdapter:
    domain = DOMAIN

    def __init__(self, engine: Engine):
        self._engine = engine

    def analytics_base_df(self, experiment_id: str | None = None) -> pd.DataFrame:
        with self._engine.connect() as conn:
            sessions = pd.read_sql(
                text(
                    "SELECT session_id, experiment_id, agent_version, external_user_id AS user_id, "
                    "outcome_label, started_at, ended_at FROM ingested_sessions WHERE domain = :domain"
                ),
                conn,
                params={"domain": self.domain},
            )
            actions = pd.read_sql(
                text(
                    "SELECT a.session_id, count(*) AS num_actions, coalesce(sum(a.latency_ms), 0) AS total_latency_ms "
                    "FROM ingested_actions a JOIN ingested_sessions s ON s.session_id = a.session_id "
                    "WHERE s.domain = :domain GROUP BY a.session_id"
                ),
                conn,
                params={"domain": self.domain},
            )
            tool_calls = pd.read_sql(
                text(
                    "SELECT tc.session_id, count(*) AS n_tool_calls, avg(tc.success::int) AS tool_success_rate "
                    "FROM ingested_tool_calls tc JOIN ingested_sessions s ON s.session_id = tc.session_id "
                    "WHERE s.domain = :domain GROUP BY tc.session_id"
                ),
                conn,
                params={"domain": self.domain},
            )
            messages = pd.read_sql(
                text(
                    "SELECT m.session_id, count(*) AS num_turns "
                    "FROM ingested_messages m JOIN ingested_sessions s ON s.session_id = m.session_id "
                    "WHERE s.domain = :domain AND m.sender = 'user' GROUP BY m.session_id"
                ),
                conn,
                params={"domain": self.domain},
            )
            metrics_long = pd.read_sql(
                text(
                    "SELECT me.session_id, me.name, me.value FROM ingested_metrics me "
                    "JOIN ingested_sessions s ON s.session_id = me.session_id WHERE s.domain = :domain"
                ),
                conn,
                params={"domain": self.domain},
            )

        if experiment_id is not None:
            sessions = sessions[sessions["experiment_id"].astype(str) == experiment_id]

        df = sessions.copy()
        df["session_id"] = df["session_id"].astype(str)
        df["experiment_id"] = df["experiment_id"].astype(str)
        df["resolved"] = (df["outcome_label"] == "resolved").astype(int)
        df["escalated"] = (df["outcome_label"] == "escalated").astype(int)
        df["abandoned"] = (df["outcome_label"] == "abandoned").astype(int)

        for extra, cols in (
            (actions, ["num_actions", "total_latency_ms"]),
            (tool_calls, ["n_tool_calls", "tool_success_rate"]),
            (messages, ["num_turns"]),
        ):
            if not extra.empty:
                extra = extra.copy()
                extra["session_id"] = extra["session_id"].astype(str)
                df = df.merge(extra, on="session_id", how="left")
            else:
                for c in cols:
                    df[c] = pd.NA
        for c in ("num_actions", "total_latency_ms", "n_tool_calls", "num_turns"):
            df[c] = df[c].fillna(0)

        if not metrics_long.empty:
            metrics_long = metrics_long.copy()
            metrics_long["session_id"] = metrics_long["session_id"].astype(str)
            metrics_wide = metrics_long.pivot_table(index="session_id", columns="name", values="value", aggfunc="first").reset_index()
            df = df.merge(metrics_wide, on="session_id", how="left")
        for metric_name in ("csat_score", "handle_time_seconds"):
            if metric_name not in df.columns:
                df[metric_name] = pd.NA

        return df

    def build_session_context(self, session_id: str) -> GenericSessionContext:
        sid = uuid.UUID(session_id)
        with self._engine.connect() as conn:
            session_row = conn.execute(
                text("SELECT session_id, outcome_label FROM ingested_sessions WHERE session_id = :sid"), {"sid": sid}
            ).mappings().first()
            if session_row is None:
                raise KeyError(f"no support session found for session_id={session_id!r}")
            messages = conn.execute(
                text("SELECT sender, text FROM ingested_messages WHERE session_id = :sid ORDER BY turn_index"), {"sid": sid}
            ).fetchall()
            actions = conn.execute(
                text("SELECT action_id, action_type FROM ingested_actions WHERE session_id = :sid ORDER BY sequence_index"), {"sid": sid}
            ).fetchall()
            tool_calls = conn.execute(
                text(
                    "SELECT tc.tool_name, tc.success, tc.error_type FROM ingested_tool_calls tc "
                    "JOIN ingested_actions a ON a.action_id = tc.action_id WHERE tc.session_id = :sid ORDER BY a.sequence_index"
                ),
                {"sid": sid},
            ).fetchall()

        return GenericSessionContext(
            session_id=session_id,
            transcript=tuple((m.sender, m.text) for m in messages),
            action_sequence=tuple(a.action_type for a in actions),
            tool_calls=tuple(GenericToolCall(tc.tool_name, bool(tc.success), tc.error_type or "none") for tc in tool_calls),
            outcome=session_row["outcome_label"],
        )

    def metric_definitions(self) -> list[MetricDefinition]:
        return list(SUPPORT_METRIC_REGISTRY)

    def metric_value_columns(self) -> dict[str, tuple[str, object]]:
        return SUPPORT_METRIC_VALUE_COLUMNS

    def guardrails(self) -> list[GuardrailDefinition]:
        return SUPPORT_GUARDRAILS

    def mechanisms(self) -> MechanismRegistry:
        return SUPPORT_MECHANISMS
