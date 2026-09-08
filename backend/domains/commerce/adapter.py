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
from sqlalchemy.engine import Engine

from backend.analytics import metric_registry
from backend.analytics.sql_runner import run_sql_file
from backend.core.attribution import MechanismRegistry
from backend.core.guardrails import GuardrailDefinition
from backend.core.metrics import MetricDefinition
from backend.domains.commerce.guardrails import COMMERCE_GUARDRAILS
from backend.domains.commerce.mechanisms import COMMERCE_MECHANISMS
from backend.domains.commerce.metrics import METRIC_VALUE_COLUMNS
from backend.llm.client import SessionContext
from backend.llm.context_builder import build_all_contexts


class CommerceAdapter:
    domain = "commerce"

    def __init__(self, engine: Engine):
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
