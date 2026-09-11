"""Small bounded LRU cache for expensive, deterministic computations keyed
on a cheap fingerprint of otherwise-unhashable inputs (dataframes, config
objects) — Stage 17 tasks 5/6 perf fixes, hardened in Stage 18 task 6.

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

    @property
    def size(self) -> int:
        """Stage 18 task 7: read-only, for the operational health
        endpoint's cache-stats section — never anything about WHAT is
        cached (a cache key can embed project/experiment ids; the health
        endpoint must stay safe to expose without leaking per-tenant
        detail), only how full the cache is."""
        return len(self._store)

    @property
    def maxsize(self) -> int:
        return self._maxsize


# Module-level singletons, deliberately shared across every caller
# (backend.app.routers.domains's GET .../metrics and GET .../investigation,
# backend.release.service's evaluate_release — used by both the on-demand
# POST .../release-evaluations endpoint and scheduled monitoring jobs) so
# the cache is warmed by whichever of them runs first, not re-paid for by
# each independently.
metrics_table_cache = BoundedCache(maxsize=64)
investigation_cache = BoundedCache(maxsize=64)


# Stage 18 task 6: the Stage 17 caches above were keyed partly on
# len(base_df) as a cheap "has the data changed" signal. That catches new
# rows arriving (ingestion, langfuse import) but silently misses an
# EXISTING row's content changing without a row-count change -- both
# backend.ingestion.service.ingest_batch (re-sending a session with the
# same external_session_id is an INSERT ... ON CONFLICT DO UPDATE, by
# design, so it can update in place) and
# backend.connectors.postgres_business.service.run_enrichment (layers
# business metrics onto EXISTING sessions via the same upsert path) do
# exactly this. A bare per-process counter, bumped once at the end of
# either write path and read into every cache key below, turns that
# silent staleness into a deterministic cache miss the next time anyone
# reads this project's data -- no content hashing (which would cost as
# much as the query it's trying to avoid paying for), no assumption that
# a row-count change is the only kind of change that matters.
class DataVersionRegistry:
    def __init__(self):
        self._versions: dict[str | None, int] = {}

    def bump(self, project_id: str | None) -> None:
        self._versions[project_id] = self._versions.get(project_id, 0) + 1

    def current(self, project_id: str | None) -> int:
        return self._versions.get(project_id, 0)


data_version_registry = DataVersionRegistry()


def metric_defs_fingerprint(metric_defs) -> tuple:
    return tuple((m.name, m.implemented, m.is_inferential) for m in metric_defs)


def investigation_config_fingerprint(config) -> tuple:
    return (
        metric_defs_fingerprint(config.metric_registry),
        tuple(g.name for g in config.guardrails),
        tuple(config.mechanisms),
        tuple(sorted((k, tuple(v)) for k, v in config.dimension_values.items())),
    )
