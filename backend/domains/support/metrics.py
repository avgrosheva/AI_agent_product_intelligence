"""The support domain's registered metrics — its own north-star metric,
outcome/funnel-equivalent metrics, a quality signal, and its one
pre-treatment segment dimension (ticket_category). Nothing here is
commerce vocabulary: `resolution_rate` is this domain's north star, the
way `conversion_rate` is commerce's.

Stage 4 (configurable metrics): loaded from metrics.json at import time
rather than hand-written Python dataclass literals — the proof that
backend.core.config.load_metric_config's config-file format is enough to
register a real domain's metrics, not just commerce's own (which stays
Python, in backend/analytics/metric_registry.py, unmigrated by choice —
Stage 4 does not require rewriting a working, already-reviewed registry).
"""

from __future__ import annotations

from pathlib import Path

from backend.core.config import load_metric_config
from backend.core.metrics import MetricDefinition

_CONFIG_PATH = Path(__file__).parent / "metrics.json"

SUPPORT_METRIC_REGISTRY: list[MetricDefinition]
SUPPORT_METRIC_VALUE_COLUMNS: dict[str, tuple[str, object]]
SUPPORT_METRIC_REGISTRY, SUPPORT_METRIC_VALUE_COLUMNS = load_metric_config(_CONFIG_PATH)
