"""CommerceAdapter: the commerce domain's DomainAdapter implementation
(Stage 3 task 4 — "commerce remains the first adapter"). Wraps the
existing commerce code paths unchanged — session_level_base.sql via
run_sql_file, backend.llm.context_builder.build_all_contexts for a
session's detector context, and the Stage 2 domain registries
(mechanisms/guardrails/metrics) — rather than reimplementing anything.
This class only proves those pieces collectively satisfy DomainAdapter;
it adds no new commerce logic.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.analytics import metric_registry
from backend.analytics.sql_runner import run_sql_file
from backend.core.attribution import MechanismRegistry, ReviewableAttribution
from backend.core.guardrails import GuardrailDefinition
from backend.core.metrics import MetricDefinition
from backend.core.session import GenericExperimentInfo
from backend.core.trajectory_config import TrajectoryConfig
from backend.domains.commerce.guardrails import COMMERCE_GUARDRAILS
from backend.domains.commerce.mechanisms import COMMERCE_MECHANISMS
from backend.domains.commerce.metrics import METRIC_VALUE_COLUMNS
from backend.domains.commerce.next_actions import NEXT_ACTION_TEMPLATES
from backend.domains.commerce.segments import DIMENSION_VALUES, PAIRWISE_ALLOWLIST
from backend.llm.client import SessionContext
from backend.llm.context_builder import build_all_contexts


class CommerceAdapter:
    domain = "commerce"

    def __init__(self, engine: Engine | None = None):
        # engine may be None when the adapter is only used for its
        # declarative methods (metric/guardrail/segment/mechanism config) —
        # e.g. building an InvestigationConfig — never for
        # analytics_base_df()/build_session_context(), which require a
        # real engine and will fail if called on one built this way.
        self._engine = engine

    def analytics_base_df(self, experiment_id: str | None = None) -> pd.DataFrame:
        df = run_sql_file(self._engine, "session_level_base.sql")
        if experiment_id is None:
            return df
        return df[df["experiment_id"].astype(str) == experiment_id]

    def build_session_context(self, session_id: str) -> SessionContext:
        contexts = build_all_contexts(self._engine, session_ids=[session_id])
        if not contexts:
            raise KeyError(f"no commerce session found for session_id={session_id!r}")
        return contexts[0]

    def metric_definitions(self) -> list[MetricDefinition]:
        return list(metric_registry.METRIC_REGISTRY)

    def metric_value_columns(self) -> dict[str, tuple[str, object]]:
        return METRIC_VALUE_COLUMNS

    def guardrails(self) -> list[GuardrailDefinition]:
        return COMMERCE_GUARDRAILS

    def mechanisms(self) -> MechanismRegistry:
        return COMMERCE_MECHANISMS

    def segment_dimensions(self) -> dict[str, list[str]]:
        return DIMENSION_VALUES

    def pairwise_segment_allowlist(self) -> list[tuple[str, str]]:
        return PAIRWISE_ALLOWLIST

    def next_action_templates(self) -> dict[str, str]:
        return NEXT_ACTION_TEMPLATES

    def list_experiments(self) -> list[GenericExperimentInfo]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT experiment_id::text AS experiment_id, name, control_version, treatment_version, "
                    "start_date::text AS start_date, end_date::text AS end_date FROM experiments ORDER BY start_date"
                )
            ).mappings().all()
        return [
            GenericExperimentInfo(
                experiment_id=r["experiment_id"], name=r["name"], control_version=r["control_version"],
                treatment_version=r["treatment_version"], start_date=r["start_date"], end_date=r["end_date"],
            )
            for r in rows
        ]

    def agent_actions_df(self, experiment_id: str | None = None) -> pd.DataFrame:
        query = "SELECT a.session_id, a.sequence_index, a.action_type::text AS action_type FROM agent_actions a"
        params: dict[str, str] = {}
        if experiment_id is not None:
            query += " JOIN sessions s ON s.session_id = a.session_id WHERE s.experiment_id::text = :eid"
            params["eid"] = experiment_id
        with self._engine.connect() as conn:
            return pd.read_sql(text(query), conn, params=params)

    def failure_attributions_wide_df(self) -> pd.DataFrame:
        mechanisms = list(COMMERCE_MECHANISMS.all_names)
        with self._engine.connect() as conn:
            long_df = pd.read_sql(
                text("SELECT session_id, failure_mode::text AS failure_mode, detected FROM session_failure_attributions"), conn
            )
        if long_df.empty:
            return pd.DataFrame(columns=["session_id", *mechanisms])
        wide = long_df.pivot_table(index="session_id", columns="failure_mode", values="detected", aggfunc="first")
        wide = wide.reindex(columns=mechanisms)
        return wide.reset_index()

    def trajectory_config(self) -> TrajectoryConfig:
        return TrajectoryConfig(
            outcome_column="outcome", negative_outcome_value="abandoned", positive_outcome_column="converted",
            clarify_action="clarify", repeat_action="search", terminal_negative_action="abandon_flow",
        )

    def list_reviewable_attributions(self, experiment_id: str | None = None, session_id: str | None = None) -> list[ReviewableAttribution]:
        query = (
            "SELECT sfa.session_id::text AS session_id, s.experiment_id::text AS experiment_id, "
            "s.agent_version::text AS agent_version, sfa.failure_mode::text AS failure_mode, "
            "sfa.detector_source::text AS detector_source, sfa.confidence, sfa.evidence_text "
            "FROM session_failure_attributions sfa JOIN sessions s ON s.session_id = sfa.session_id "
            "WHERE sfa.detected = true"
        )
        params: dict[str, str] = {}
        if experiment_id is not None:
            query += " AND s.experiment_id::text = :eid"
            params["eid"] = experiment_id
        if session_id is not None:
            query += " AND sfa.session_id::text = :sid"
            params["sid"] = session_id
        with self._engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()
        return [
            ReviewableAttribution(
                session_id=r["session_id"], experiment_id=r["experiment_id"], agent_version=r["agent_version"],
                failure_mode=r["failure_mode"], detector_source=r["detector_source"],
                confidence=r["confidence"], evidence_text=r["evidence_text"],
            )
            for r in rows
        ]
