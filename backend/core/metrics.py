"""Generic metric-definition shape (Stage 2: domain-agnostic core).

`backend.analytics.metric_registry.MetricDefinition` is already fully
domain-agnostic in its own shape (name, semantic_class, source_tables,
numerator/denominator description, eligibility_rule, statistical
properties) — it is metadata describing a metric, not executable logic
tied to shopping. Re-exported here under backend.core so "metric" appears
as a named core concept without moving or duplicating the dataclass.

What is NOT generic, and stays in the commerce domain, is which metrics
are actually registered (backend.analytics.metric_registry.METRIC_REGISTRY,
a plain list — a second domain would populate its own) and the binding
from a metric's name to the actual session-level column that holds its
value (backend.domains.commerce.metrics.METRIC_VALUE_COLUMNS). A second
domain defines its own north-star metric, funnel/outcome metrics, and
guardrails by registering its own MetricDefinition entries and its own
value-column mapping — the mechanism computing a metric from those
(backend.analytics.experiment_results.analyze_metric) does not change.
"""

from __future__ import annotations

from backend.analytics.metric_registry import MetricDefinition

__all__ = ["MetricDefinition", "get_metric"]


def get_metric(name: str, registry: list[MetricDefinition]) -> MetricDefinition:
    """Stage 4: the domain-scoped version of
    backend.analytics.metric_registry.get() — looks a metric up in
    whichever registry the caller passed (a DomainAdapter's own
    metric_definitions()), rather than the global commerce
    METRIC_REGISTRY. metric_registry.get() itself now delegates here for
    backward compatibility."""
    for m in registry:
        if m.name == name:
            return m
    raise KeyError(f"No metric registered as {name!r}")
