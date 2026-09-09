"""Stage 7 tasks 5-6: compute_economics — the one deterministic function
every domain's release evaluation runs through. Every returned field is
independently nullable: a domain that declares a cost_column but not a
value_column still gets real cost figures with business_impact left null,
and a domain whose declared column isn't actually present in this
particular analytics_base_df (e.g. a metric nobody happened to ingest for
this batch) degrades the same way rather than raising.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from backend.economics.config import EconomicsConfig


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


@dataclass(frozen=True)
class EconomicsResult:
    cost_per_session_v1: float | None = None
    cost_per_session_v2: float | None = None
    cost_per_success_v1: float | None = None
    cost_per_success_v2: float | None = None
    estimated_incremental_cost_per_session: float | None = None
    value_per_success_v1: float | None = None
    value_per_success_v2: float | None = None
    estimated_business_impact_per_session: float | None = None
    notes: list[str] = field(default_factory=list)


def compute_economics(df: pd.DataFrame, config: EconomicsConfig | None) -> EconomicsResult | None:
    """Returns None only when the domain declares no economics config at
    all (backend.core.adapter.DomainAdapter.economics_config() -> None) —
    a domain that HAS a config but is missing some of its columns in this
    particular dataframe still gets a result, just with those specific
    fields null."""
    if config is None:
        return None

    notes: list[str] = []
    v1 = df[df["agent_version"] == "v1"]
    v2 = df[df["agent_version"] == "v2"]

    has_cost = bool(config.cost_column) and config.cost_column in df.columns
    if not has_cost:
        notes.append("cost data unavailable for this domain/dataset")

    cost_per_session_v1 = _safe_float(v1[config.cost_column].mean()) if has_cost and len(v1) else None
    cost_per_session_v2 = _safe_float(v2[config.cost_column].mean()) if has_cost and len(v2) else None

    success_v1 = v1[v1[config.success_column] == 1] if config.success_column in df.columns else v1.iloc[0:0]
    success_v2 = v2[v2[config.success_column] == 1] if config.success_column in df.columns else v2.iloc[0:0]

    cost_per_success_v1 = _safe_float(success_v1[config.cost_column].mean()) if has_cost and len(success_v1) else None
    cost_per_success_v2 = _safe_float(success_v2[config.cost_column].mean()) if has_cost and len(success_v2) else None

    estimated_incremental_cost_per_session = None
    if cost_per_session_v1 is not None and cost_per_session_v2 is not None:
        estimated_incremental_cost_per_session = cost_per_session_v2 - cost_per_session_v1

    has_value = bool(config.value_column) and config.value_column in df.columns
    if not has_value:
        notes.append("revenue/value data unavailable for this domain/dataset")

    value_per_success_v1 = _safe_float(success_v1[config.value_column].mean()) if has_value and len(success_v1) else None
    value_per_success_v2 = _safe_float(success_v2[config.value_column].mean()) if has_value and len(success_v2) else None

    estimated_business_impact_per_session = None
    if has_value and has_cost and config.success_column in df.columns:
        success_rate_v1 = _safe_float(v1[config.success_column].mean()) if len(v1) else None
        success_rate_v2 = _safe_float(v2[config.success_column].mean()) if len(v2) else None
        if None not in (success_rate_v1, success_rate_v2, value_per_success_v1, value_per_success_v2, cost_per_session_v1, cost_per_session_v2):
            net_value_v1 = success_rate_v1 * value_per_success_v1 - cost_per_session_v1
            net_value_v2 = success_rate_v2 * value_per_success_v2 - cost_per_session_v2
            estimated_business_impact_per_session = net_value_v2 - net_value_v1

    return EconomicsResult(
        cost_per_session_v1=cost_per_session_v1,
        cost_per_session_v2=cost_per_session_v2,
        cost_per_success_v1=cost_per_success_v1,
        cost_per_success_v2=cost_per_success_v2,
        estimated_incremental_cost_per_session=estimated_incremental_cost_per_session,
        value_per_success_v1=value_per_success_v1,
        value_per_success_v2=value_per_success_v2,
        estimated_business_impact_per_session=estimated_business_impact_per_session,
        notes=notes,
    )
