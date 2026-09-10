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

from backend.core.analysis_window import AnalysisWindow
from backend.core.attribution import MechanismRegistry, ReviewableAttribution
from backend.economics.config import EconomicsConfig
from backend.core.guardrails import GuardrailDefinition
from backend.core.metrics import MetricDefinition
from backend.core.session import CoreSessionContext, GenericExperimentInfo
from backend.core.trajectory_config import TrajectoryConfig


class DomainAdapter(Protocol):
    domain: str

    def analytics_base_df(self, experiment_id: str | None = None, window: AnalysisWindow | None = None) -> pd.DataFrame:
        """One row per session, with at minimum: session_id, experiment_id,
        agent_version, and whatever generic outcome/metric columns this
        domain's metric_value_columns() references.

        Stage 13 task 1/3: `window`, when given, restricts sessions to
        `started_at >= window.start AND started_at <= window.end`
        (backend.core.analysis_window.AnalysisWindow — the one
        consistent rule, applied here so every caller — metrics,
        guardrails, investigation, segment scan, economics, evidence —
        sees the same windowed data without knowing about windows
        itself. `None` (the default) means the full dataset, unchanged
        from before this existed (Stage 13 task 4)."""
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

    def segment_dimensions(self) -> dict[str, list[str]]:
        """dimension_name -> allowed values, for every pre_treatment
        MetricDefinition this domain registers (Stage 4 task 1/2). May be
        an empty dict — a domain with no pre-treatment dimension registered
        simply has no segment scan (the investigation pipeline degrades to
        an empty scan, not an error)."""
        ...

    def pairwise_segment_allowlist(self) -> list[tuple[str, str]]:
        """Curated two-dimension segment pairs to additionally scan (never
        the full combinatorial grid). May be empty."""
        ...

    def next_action_templates(self) -> dict[str, str]:
        """failure_mode -> remediation prose, keyed the same way as
        mechanisms().all_names, plus "other"/"none". May return an empty
        dict (or None) to fall back to backend.core.next_actions.
        GENERIC_NEXT_ACTION_TEMPLATES — the domain-provided-or-generic
        choice Stage 4 task 1 requires."""
        ...

    def list_experiments(self) -> list[GenericExperimentInfo]:
        """Stage 5: every experiment this domain has data for — the
        generic /domains/{domain}/experiments listing's only data source."""
        ...

    def agent_actions_df(self, experiment_id: str | None = None, window: AnalysisWindow | None = None) -> pd.DataFrame:
        """Columns: session_id, sequence_index, action_type — the same
        shape backend.investigation.trajectory_attribution.
        reconstruct_trajectories already expects. Empty (but correctly
        shaped) is valid for a domain that never registers a mechanism and
        so never runs trajectory attribution.

        `window` restricts to actions whose OWN session falls inside the
        window (same rule as analytics_base_df) — trajectory
        reconstruction must never see an action from a session the
        windowed metrics/guardrails themselves excluded."""
        ...

    def failure_attributions_wide_df(self) -> pd.DataFrame:
        """One row per session_id, one boolean column per
        mechanisms().all_names entry (NaN = not evaluated). A domain with
        an empty MechanismRegistry returns an empty frame with just the
        session_id join key (Stage 3 task 7) — run_investigation treats
        that as a no-op merge."""
        ...

    def trajectory_config(self) -> TrajectoryConfig:
        """Stage 5 task 5: which outcome/action-type literals trajectory
        attribution looks for, for THIS domain. Unused (but still must
        return a coherent object) for a domain with no registered
        mechanisms, since that code path is never reached for it."""
        ...

    def list_reviewable_attributions(self, experiment_id: str | None = None, session_id: str | None = None) -> list[ReviewableAttribution]:
        """Stage 6 task 3/5: every detected=true mechanism instance a human
        analyst could review, optionally scoped to one experiment and/or
        one session. May be empty for a domain with no attribution storage
        (support — no mechanisms registered, nothing to review)."""
        ...

    def economics_config(self) -> EconomicsConfig | None:
        """Stage 7 tasks 5-6: which analytics_base_df columns hold this
        domain's cost/success/value data. None if this domain has no
        economics concept configured at all — backend.economics.compute.
        compute_economics then returns None outright rather than a
        result full of nulls."""
        ...
