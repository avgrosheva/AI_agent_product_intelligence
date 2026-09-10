"""Stage 12 tasks 4/7: what a DomainAdapter calls to check for a
persisted override before falling back to its own static Python/JSON
default. Each function returns None when nothing is persisted for that
one field — the adapter's existing static default applies unchanged,
which is how commerce/support stay backward-compatible (task 7)."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from backend.core.config import load_guardrail_config_from_dict, load_metric_config_from_dict
from backend.core.guardrails import GuardrailDefinition
from backend.core.metrics import MetricDefinition
from backend.economics.config import EconomicsConfig
from backend.project_config.service import get_project_config


def metrics_override(engine: Engine, project_id: str) -> tuple[list[MetricDefinition], dict[str, tuple[str, object]]] | None:
    config = get_project_config(engine, project_id)
    if config is None or config.metrics is None:
        return None
    return load_metric_config_from_dict(config.metrics)


def guardrails_override(engine: Engine, project_id: str) -> list[GuardrailDefinition] | None:
    config = get_project_config(engine, project_id)
    if config is None or config.guardrails is None:
        return None
    return load_guardrail_config_from_dict(config.guardrails)


def segment_dimensions_override(engine: Engine, project_id: str) -> dict[str, list[str]] | None:
    config = get_project_config(engine, project_id)
    if config is None or config.segment_dimensions is None:
        return None
    return config.segment_dimensions


def economics_override(engine: Engine, project_id: str) -> EconomicsConfig | None:
    config = get_project_config(engine, project_id)
    if config is None or config.economics is None:
        return None
    e = config.economics
    return EconomicsConfig(cost_column=e.get("cost_column"), success_column=e["success_column"], value_column=e.get("value_column"))
