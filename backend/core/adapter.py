"""Generic domain adapter interface (Stage 3 task 4).

A `DomainAdapter` is what a domain supplies to plug into the shared
analytics/attribution core: a session-level analytics dataframe (the
generic subset of what commerce's session_level_base.sql produces), a way
to build a detector-ready context for one session, its own metric
definitions and metric-name-to-column bindings, its own guardrails, and
its own registered failure mechanisms (which may be an EMPTY registry —
Stage 3 task 7: a domain with no relevant detector simply configures
none, rather than inheriting commerce's six).

Commerce (backend.domains.commerce.adapter.CommerceAdapter) is the first
implementation, wrapping the existing commerce code paths unchanged.
backend.domains.support.adapter.SupportAdapter is the second, proving a
non-commerce domain can plug in without touching this file or any
commerce module.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from backend.core.attribution import MechanismRegistry
from backend.core.guardrails import GuardrailDefinition
from backend.core.metrics import MetricDefinition
from backend.core.session import CoreSessionContext


class DomainAdapter(Protocol):
    domain: str

    def analytics_base_df(self, experiment_id: str | None = None) -> pd.DataFrame:
        """One row per session, with at minimum: session_id, experiment_id,
        agent_version, and whatever generic outcome/metric columns this
        domain's metric_value_columns() references."""
        ...

    def build_session_context(self, session_id: str) -> CoreSessionContext:
        """A detector-ready context for one session — satisfies
        CoreSessionContext at minimum; a domain may return a richer object
        (like commerce's SessionContext) with domain-specific fields on top."""
        ...

    def metric_definitions(self) -> list[MetricDefinition]: ...

    def metric_value_columns(self) -> dict[str, tuple[str, object]]:
        """metric_name -> (column_in_analytics_base_df, eligibility_fn|None) —
        the same shape backend.analytics.experiment_results.analyze_metric
        already expects, so that function works unchanged for any domain."""
        ...

    def guardrails(self) -> list[GuardrailDefinition]: ...

    def mechanisms(self) -> MechanismRegistry:
        """May be an empty MechanismRegistry([]) — not every domain has a
        relevant automatic failure detector."""
        ...
