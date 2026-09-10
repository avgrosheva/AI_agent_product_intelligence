"""SupportAdapter: the support domain's DomainAdapter implementation
(Stage 3 task 6's proof fixture). Reads exclusively from the generic
ingestion tables (backend.ingestion.models) — never products/
recommendations/product_events, and never any commerce ORM model."""

from __future__ import annotations

import uuid

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.core.analysis_window import AnalysisWindow
from backend.core.attribution import MechanismRegistry, ReviewableAttribution
from backend.economics.config import EconomicsConfig
from backend.core.guardrails import GuardrailDefinition
from backend.core.metrics import MetricDefinition
from backend.core.next_actions import GENERIC_NEXT_ACTION_TEMPLATES
from backend.core.session import GenericExperimentInfo, GenericSessionContext, GenericToolCall
from backend.core.trajectory_config import TrajectoryConfig
from backend.domains.support.guardrails import SUPPORT_GUARDRAILS
from backend.domains.support.mechanisms import SUPPORT_MECHANISMS
from backend.domains.support.metrics import SUPPORT_METRIC_REGISTRY, SUPPORT_METRIC_VALUE_COLUMNS

DOMAIN = "support"

# Stage 4 task 2/5: the support domain's one pre-treatment segment
# dimension — set at ticket intake, before any agent action, mirroring
# commerce's requested_category. Fixed here as data (same shape as
# backend.domains.commerce.segments.DIMENSION_VALUES) rather than
# discovered from live data, so the segment scan is bounded and every
# surfaced segment stays explainable in one sentence, same as commerce.
SEGMENT_DIMENSION_VALUES: dict[str, list[str]] = {
    "ticket_category": ["billing", "technical", "account_access", "shipping_status", "general_inquiry"],
}


class SupportAdapter:
    domain = DOMAIN

    def __init__(self, engine: Engine, project_id: str | None = None):
        # Stage 7 task 2: when given, every query below is scoped to
        # experiments that belong to this project (via a join to
        # ingested_experiments.project_id) — the tenancy boundary for the
        # ingestion-based domains, where project_id is a real, enforced
        # column (unlike commerce's single shared dataset — see
        # CommerceAdapter's own project_id parameter for why it's a no-op
        # there).
        self._engine = engine
        self._project_id = project_id

    def _project_filter(self, params: dict, experiment_alias: str = "e") -> str:
        if self._project_id is None:
            return ""
        params["project_id"] = self._project_id
        return f" AND {experiment_alias}.project_id = :project_id"

    def analytics_base_df(self, experiment_id: str | None = None, window: AnalysisWindow | None = None) -> pd.DataFrame:
        with self._engine.connect() as conn:
            params: dict[str, object] = {"domain": self.domain}
            query = (
                "SELECT s.session_id, s.experiment_id, s.agent_version, s.external_user_id AS user_id, "
                "s.outcome_label, s.started_at, s.ended_at, s.context->>'ticket_category' AS ticket_category "
                "FROM ingested_sessions s JOIN ingested_experiments e ON e.experiment_id = s.experiment_id "
                "WHERE s.domain = :domain"
            )
            query += self._project_filter(params)
            # Stage 13 tasks 1-2: the one consistent window rule --
            # started_at >= start AND started_at <= end, inclusive both
            # ends -- applied here so metrics/guardrails/investigation/
            # segment scan/economics/evidence all see the same windowed
            # rows without any of them knowing a window exists.
            if window is not None:
                query += " AND s.started_at >= :window_start AND s.started_at <= :window_end"
                params["window_start"] = window.start
                params["window_end"] = window.end
            sessions = pd.read_sql(text(query), conn, params=params)
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
            params: dict[str, object] = {"sid": sid}
            query = "SELECT s.session_id, s.outcome_label FROM ingested_sessions s JOIN ingested_experiments e ON e.experiment_id = s.experiment_id WHERE s.session_id = :sid"
            query += self._project_filter(params, experiment_alias="e")
            session_row = conn.execute(text(query), params).mappings().first()
            if session_row is None:
                # Cross-project lookup fails exactly like "doesn't exist" —
                # never distinguishes "wrong project" from "no such
                # session" (Stage 7 task 2: prevent cross-project access).
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

    def _metrics_override(self):
        # Stage 12 task 4/7: a project's own persisted metrics config
        # (backend.project_config) takes priority over this domain's
        # static metrics.json; absent one, behavior is unchanged.
        if self._engine is None or self._project_id is None:
            return None
        from backend.project_config.overrides import metrics_override

        return metrics_override(self._engine, self._project_id)

    def metric_definitions(self) -> list[MetricDefinition]:
        override = self._metrics_override()
        return override[0] if override is not None else list(SUPPORT_METRIC_REGISTRY)

    def metric_value_columns(self) -> dict[str, tuple[str, object]]:
        override = self._metrics_override()
        return override[1] if override is not None else SUPPORT_METRIC_VALUE_COLUMNS

    def guardrails(self) -> list[GuardrailDefinition]:
        if self._engine is not None and self._project_id is not None:
            from backend.project_config.overrides import guardrails_override

            override = guardrails_override(self._engine, self._project_id)
            if override is not None:
                return override
        return SUPPORT_GUARDRAILS

    def mechanisms(self) -> MechanismRegistry:
        return SUPPORT_MECHANISMS

    def segment_dimensions(self) -> dict[str, list[str]]:
        if self._engine is not None and self._project_id is not None:
            from backend.project_config.overrides import segment_dimensions_override

            override = segment_dimensions_override(self._engine, self._project_id)
            if override is not None:
                return override
        return SEGMENT_DIMENSION_VALUES

    def pairwise_segment_allowlist(self) -> list[tuple[str, str]]:
        # Only one pre-treatment dimension is registered, so there is no
        # pair to curate — an empty allowlist, not the (impossible) full grid.
        return []

    def next_action_templates(self) -> dict[str, str]:
        # No mechanisms registered (see mechanisms() above) means a
        # finding's dominant_failure_mode is always None -> "none": the
        # generic fallback is genuinely all this domain needs, proving the
        # "domain-provided OR generic" choice (Stage 4 task 1).
        return GENERIC_NEXT_ACTION_TEMPLATES

    def list_experiments(self) -> list[GenericExperimentInfo]:
        params: dict[str, str] = {"domain": self.domain}
        query = (
            "SELECT experiment_id::text AS experiment_id, name, control_version, treatment_version, "
            "start_date::text AS start_date, end_date::text AS end_date FROM ingested_experiments e "
            "WHERE domain = :domain"
        )
        query += self._project_filter(params, experiment_alias="e")
        query += " ORDER BY start_date"
        with self._engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()
        return [
            GenericExperimentInfo(
                experiment_id=r["experiment_id"], name=r["name"], control_version=r["control_version"],
                treatment_version=r["treatment_version"], start_date=r["start_date"], end_date=r["end_date"],
            )
            for r in rows
        ]

    def agent_actions_df(self, experiment_id: str | None = None, window: AnalysisWindow | None = None) -> pd.DataFrame:
        params: dict[str, object] = {"domain": self.domain}
        query = (
            "SELECT a.session_id, a.sequence_index, a.action_type FROM ingested_actions a "
            "JOIN ingested_sessions s ON s.session_id = a.session_id "
            "JOIN ingested_experiments e ON e.experiment_id = s.experiment_id "
            "WHERE s.domain = :domain"
        )
        query += self._project_filter(params, experiment_alias="e")
        if experiment_id is not None:
            query += " AND s.experiment_id::text = :eid"
            params["eid"] = experiment_id
        if window is not None:
            query += " AND s.started_at >= :window_start AND s.started_at <= :window_end"
            params["window_start"] = window.start
            params["window_end"] = window.end
        with self._engine.connect() as conn:
            df = pd.read_sql(text(query), conn, params=params)
        df["session_id"] = df["session_id"].astype(str)
        return df

    def failure_attributions_wide_df(self) -> pd.DataFrame:
        # No generic failure-attribution storage exists for this domain
        # (mechanisms() is empty — Stage 3 task 7): an empty frame with
        # just the join key is what run_investigation expects in that case.
        return pd.DataFrame(columns=["session_id"])

    def trajectory_config(self) -> TrajectoryConfig:
        # Unreached in practice (mechanisms() is empty, so
        # run_investigation never evaluates trajectory associations for
        # this domain — see pipeline.py's `if config.mechanisms:` guard),
        # but still a coherent, domain-appropriate config rather than
        # commerce's literals: this domain's own outcome/action vocabulary.
        return TrajectoryConfig(
            outcome_column="outcome_label", negative_outcome_value="abandoned", positive_outcome_column="resolved",
            clarify_action="clarify", repeat_action="triage_ticket", terminal_negative_action="escalate",
        )

    def list_reviewable_attributions(self, experiment_id: str | None = None, session_id: str | None = None) -> list[ReviewableAttribution]:
        # No generic failure-attribution storage exists for this domain
        # (mechanisms() is empty — Stage 3 task 7): nothing to review.
        return []

    def economics_config(self) -> EconomicsConfig:
        # "resolved" is a real 0/1 column this adapter always produces.
        # cost_usd/revenue_usd are declared optimistically — they are only
        # ACTUALLY present in analytics_base_df() if a caller ingested a
        # metric with that exact name (backend.ingestion; the metrics-long
        # pivot in analytics_base_df() surfaces whatever names exist).
        # backend.economics.compute.compute_economics checks column
        # presence itself and returns null fields rather than raising when
        # a particular batch didn't include them (Stage 7 task 6).
        if self._engine is not None and self._project_id is not None:
            from backend.project_config.overrides import economics_override

            override = economics_override(self._engine, self._project_id)
            if override is not None:
                return override
        return EconomicsConfig(cost_column="cost_usd", success_column="resolved", value_column="revenue_usd")
