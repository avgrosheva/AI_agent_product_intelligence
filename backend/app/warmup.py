"""Optional startup cache warm-up for the portfolio demo (Stage 5 review
correction #3).

Problem: /metrics and /investigation recompute their full result on every
call (backend.app.routers.experiments._get_full_metric_table_cached and
backend.app.routers.investigation._run_investigation_cached are in-process
lru_cache wrappers — see Stage 5 SS13). The first call after a fresh server
start is therefore a genuine 24-30s recomputation at demo scale, which is a
poor first impression for a live portfolio demo even though every
subsequent call is sub-2s.

Fix: precompute the same cached functions once at application startup,
before the server accepts traffic, so the first real user request already
hits a warm cache. This is plain in-process memoization (the same
lru_cache already used everywhere else in backend.app) run eagerly instead
of lazily — no new caching service, no Redis/Celery, no changes to the
analytics/investigation pipelines themselves, which remain the source of
truth.

Gating: warm-up is opt-in via the AIPI_WARMUP_ON_STARTUP environment
variable (unset/"0"/"false" = disabled). It must stay opt-in because dev
scale is fast enough that eager warm-up is pointless there, and because
every test that boots the FastAPI app (via TestClient) must not pay a
demo-scale warm-up cost or depend on a particular experiment already
existing in the database at import time.

Cache lifecycle (also documented in backend.app.dependencies): every
cached value here is valid only for the lifetime of this Python process
and only for the dataset that was loaded in Postgres when the process
started. There is no invalidation path — Stage 4 established there is no
write path that mutates sessions/agent_actions/failure_labels after load,
so none was built. If the underlying experiment data changes (a fresh
`datagen.load_to_postgres` run, a different profile, reclassification),
the server process must be restarted so the caches are recomputed against
the new data; warming up against stale data and leaving the process
running would silently serve stale results.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Iterable

from sqlalchemy import text

logger = logging.getLogger("backend.app.warmup")

WARMUP_LENSES: tuple[str, ...] = ("abandonment", "conversion", "constraint_satisfaction")


def warmup_enabled() -> bool:
    return os.environ.get("AIPI_WARMUP_ON_STARTUP", "").strip().lower() in {"1", "true", "yes", "on"}


def _experiment_ids() -> list[str]:
    from backend.app.dependencies import get_engine

    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT experiment_id::text AS experiment_id FROM experiments ORDER BY experiment_id")).all()
    return [r.experiment_id for r in rows]


def warm_up_cache(experiment_ids: Iterable[str] | None = None) -> dict:
    """Populate the metric-table and investigation caches for every
    experiment currently in the database (or the given ids), for the
    three lenses the API exposes. Returns per-step timings in seconds so
    callers (the startup hook, or a manual re-warm) can report them."""
    from backend.app.routers.experiments import _get_full_metric_table_cached
    from backend.app.routers.investigation import _run_investigation_cached

    ids = list(experiment_ids) if experiment_ids is not None else _experiment_ids()
    timings: dict[str, float] = {}
    t_start = time.time()

    for eid in ids:
        t0 = time.time()
        _get_full_metric_table_cached(eid)
        timings[f"metrics[{eid}]"] = time.time() - t0

        for lens in WARMUP_LENSES:
            t0 = time.time()
            _run_investigation_cached(eid, lens)
            timings[f"investigation[{eid},{lens}]"] = time.time() - t0

    timings["total"] = time.time() - t_start
    return timings


def _print(msg: str) -> None:
    # Plain print() is block-buffered when stdout is redirected to a file
    # (the common case for a deployed/backgrounded uvicorn process), so
    # without an explicit flush these lines can sit in memory and never
    # reach the log until the process exits — flush every line so warm-up
    # progress is visible in real time.
    print(msg, flush=True)


def run_startup_warmup() -> None:
    if not warmup_enabled():
        _print("[warmup] AIPI_WARMUP_ON_STARTUP not set — skipping demo cache warm-up (lazy, per-request caching still applies).")
        return

    _print("[warmup] AIPI_WARMUP_ON_STARTUP set — precomputing metric table and all 3 investigation lenses for every experiment...")
    try:
        timings = warm_up_cache()
    except Exception:
        logger.exception("Demo cache warm-up failed; server will still start and fall back to lazy per-request computation.")
        _print("[warmup] FAILED — server will still start and fall back to lazy per-request computation.")
        return

    for name, seconds in timings.items():
        if name != "total":
            _print(f"[warmup]   {name}: {seconds:.2f}s")
    _print(f"[warmup] Demo cache warm-up complete in {timings.get('total', 0.0):.2f}s — subsequent /metrics and /investigation requests will be served from cache.")
