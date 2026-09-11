"""Small bounded LRU cache for expensive, deterministic computations keyed
on a cheap fingerprint of otherwise-unhashable inputs (dataframes, config
objects) — Stage 17 tasks 5/6 perf fixes.

Not domain-specific and not tied to one call path: both the generic
domain router (GET .../metrics, GET .../investigation) and
backend.release.service (POST .../release-evaluations, and scheduled
monitoring jobs) run the exact same underlying statistical computation
for the exact same (domain, project, experiment, primary_metric,
data-shape) key. A cache instance defined once here and shared by both
callers means a "GET investigation" and a later "Evaluate now" for the
same experiment reuse each other's work instead of each paying for the
full computation independently — this is what caught the second, deeper
bottleneck: backend.release.service.evaluate_release previously bypassed
the router-local cache entirely (it doesn't call through the router), so
a single "Evaluate now" click cost ~64s even after GET .../investigation
was already fast.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Callable, TypeVar

T = TypeVar("T")


class BoundedCache:
    def __init__(self, maxsize: int = 64):
        self._maxsize = maxsize
        self._store: OrderedDict[tuple, object] = OrderedDict()

    def get_or_compute(self, key: tuple, compute: Callable[[], T]) -> T:
        cached = self._store.get(key)
        if cached is not None:
            self._store.move_to_end(key)
            return cached
        result = compute()
        self._store[key] = result
        if len(self._store) > self._maxsize:
            self._store.popitem(last=False)
        return result


# Module-level singletons, deliberately shared across every caller
# (backend.app.routers.domains's GET .../metrics and GET .../investigation,
# backend.release.service's evaluate_release — used by both the on-demand
# POST .../release-evaluations endpoint and scheduled monitoring jobs) so
# the cache is warmed by whichever of them runs first, not re-paid for by
# each independently.
metrics_table_cache = BoundedCache(maxsize=64)
investigation_cache = BoundedCache(maxsize=64)


def metric_defs_fingerprint(metric_defs) -> tuple:
    return tuple((m.name, m.implemented, m.is_inferential) for m in metric_defs)


def investigation_config_fingerprint(config) -> tuple:
    return (
        metric_defs_fingerprint(config.metric_registry),
        tuple(g.name for g in config.guardrails),
        tuple(config.mechanisms),
        tuple(sorted((k, tuple(v)) for k, v in config.dimension_values.items())),
    )
