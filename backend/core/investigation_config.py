"""Stage 4: the declarative bundle backend.investigation.pipeline.run_investigation
needs to run for ANY domain — every piece the pipeline used to import
directly from the commerce domain (segment dimensions/allowlist, metric
registry/value-columns, guardrails, mechanisms, next-action templates),
now supplied explicitly by the caller instead.

`investigation_config_from_adapter` builds one of these from any
DomainAdapter — the pipeline itself never imports a domain module to get
here; the adapter is the only thing that does.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.core.adapter import DomainAdapter
from backend.core.guardrails import GuardrailDefinition
from backend.core.metrics import MetricDefinition
from backend.core.next_actions import GENERIC_NEXT_ACTION_TEMPLATES
from backend.core.trajectory_config import TrajectoryConfig


@dataclass(frozen=True)
class InvestigationConfig:
    metric_registry: list[MetricDefinition]
    metric_value_columns: dict[str, tuple[str, object]]
    guardrails: list[GuardrailDefinition]
    mechanisms: tuple[str, ...]
    dimension_values: dict[str, list[str]]
    pairwise_allowlist: list[tuple[str, str]]
    pre_treatment_dimensions: list[str]
    next_action_templates: dict[str, str]
    trajectory_config: TrajectoryConfig


def investigation_config_from_adapter(adapter: DomainAdapter) -> InvestigationConfig:
    definitions = adapter.metric_definitions()
    pre_treatment = [m.name for m in definitions if m.semantic_class == "pre_treatment"]
    next_action_templates = adapter.next_action_templates() or GENERIC_NEXT_ACTION_TEMPLATES
    return InvestigationConfig(
        metric_registry=definitions,
        metric_value_columns=adapter.metric_value_columns(),
        guardrails=adapter.guardrails(),
        mechanisms=adapter.mechanisms().all_names,
        dimension_values=adapter.segment_dimensions(),
        pairwise_allowlist=adapter.pairwise_segment_allowlist(),
        pre_treatment_dimensions=pre_treatment,
        next_action_templates=next_action_templates,
        trajectory_config=adapter.trajectory_config(),
    )
