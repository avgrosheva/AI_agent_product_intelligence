"""Stage 4 task 3/4: load metrics and guardrails from a simple JSON
config file instead of hand-written Python dataclass literals.

Deliberately NOT a rules engine — eligibility is one of three named,
closed-vocabulary rule kinds (not_null / equals / gte), the same "small
fixed set of named strategies, not arbitrary code" approach
backend.core.guardrails already uses for aggregation/comparison. A domain
is still free to register MetricDefinition/GuardrailDefinition objects by
hand in Python (as commerce does) — this loader is an alternative path
into the exact same shapes, proven end to end by the support domain
(backend/domains/support/metrics.json, guardrails.json).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pandas as pd

from backend.core.guardrails import GuardrailDefinition
from backend.core.metrics import MetricDefinition

EligibilityKind = str  # "not_null" | "equals" | "gte"


def _eligibility_fn(rule: dict | None) -> Callable[[pd.DataFrame], pd.Series] | None:
    if rule is None:
        return None
    kind = rule["kind"]
    column = rule["column"]
    if kind == "not_null":
        return lambda df, c=column: df[c].notna()
    if kind == "equals":
        value = rule["value"]
        return lambda df, c=column, v=value: df[c] == v
    if kind == "gte":
        value = rule["value"]
        return lambda df, c=column, v=value: df[c] >= v
    raise ValueError(f"unknown eligibility rule kind: {kind!r} (must be one of: not_null, equals, gte)")


def load_metric_config(path: str | Path) -> tuple[list[MetricDefinition], dict[str, tuple[str, object]]]:
    """Returns (metric_definitions, metric_value_columns) — the exact two
    shapes DomainAdapter.metric_definitions()/metric_value_columns()
    already return, so analyze_metric() does not change."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    definitions: list[MetricDefinition] = []
    value_columns: dict[str, tuple[str, object]] = {}

    for entry in data["metrics"]:
        name = entry["name"]
        eligibility = entry.get("eligibility")
        metric_type = entry.get("type", "rate")
        definitions.append(
            MetricDefinition(
                name=name,
                label=entry.get("label", name),
                metric_type=metric_type,
                direction=entry.get("direction", "higher_is_better"),
                semantic_class=entry.get("semantic_class", "outcome"),
                source_tables=tuple(entry.get("source_tables", ())),
                unit_of_measurement=entry.get("unit_of_measurement", entry.get("label", name)),
                unit_of_inference=entry.get("inference_unit", "user"),
                numerator=entry.get("numerator", "n/a"),
                denominator=entry.get("denominator", "n/a"),
                eligibility_rule=json.dumps(eligibility) if eligibility else "all sessions",
                is_descriptive=entry.get("is_descriptive", True),
                is_inferential=entry.get("is_inferential", True),
                cluster_stat_shape=entry.get("cluster_stat_shape", "symmetric" if metric_type != "continuous_skewed" else "skewed"),
                implemented=True,
                is_rate_metric=metric_type == "rate",
                notes=entry.get("notes", ""),
            )
        )
        value_column = entry.get("value_column")
        if value_column:
            value_columns[name] = (value_column, _eligibility_fn(eligibility))

    return definitions, value_columns


def load_guardrail_config(path: str | Path) -> list[GuardrailDefinition]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        GuardrailDefinition(
            name=entry["name"],
            metric=entry.get("metric", ""),
            column=entry["column"],
            aggregation=entry["aggregation"],
            kind=entry.get("kind", "ratio"),
            direction=entry.get("direction", "increase_is_bad"),
            threshold=entry["threshold"],
            severity=entry.get("severity", "blocking"),
            enabled=entry.get("enabled", True),
            dropna=entry.get("dropna", False),
        )
        for entry in data["guardrails"]
    ]
