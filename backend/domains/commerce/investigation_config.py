"""Stage 4: the commerce domain's InvestigationConfig — the concrete
config every current commerce call site (the /investigation API, the
/experiments guardrail endpoints, and the offline report/validation
scripts) passes into the now-generic
backend.investigation.pipeline.run_investigation, so commerce's own
behavior is unchanged now that the pipeline no longer defaults to
commerce data internally.

Built from CommerceAdapter's declarative methods only (metric_definitions,
metric_value_columns, guardrails, mechanisms, segment_dimensions,
pairwise_segment_allowlist, next_action_templates) — none of which touch
the database — computed once at import time since it is static Python
data, not a live query.
"""

from __future__ import annotations

from backend.core.investigation_config import InvestigationConfig, investigation_config_from_adapter
from backend.domains.commerce.adapter import CommerceAdapter

COMMERCE_INVESTIGATION_CONFIG: InvestigationConfig = investigation_config_from_adapter(CommerceAdapter())


def commerce_investigation_config() -> InvestigationConfig:
    return COMMERCE_INVESTIGATION_CONFIG
