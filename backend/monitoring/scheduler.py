"""Stage 11 task 1: "use background jobs, not request-blocking loops."
A lightweight, dependency-free polling thread — proportionate to this
project's scale, matching the existing opt-in-background-work precedent
(backend.app.warmup, gated behind AIPI_WARMUP_ON_STARTUP) rather than
pulling in Celery/RQ/APScheduler for a handful of periodic checks.

Disabled by default (AIPI_MONITORING_SCHEDULER=1 to enable) so normal
dev startup and the test suite are unaffected — tests call
backend.monitoring.service.run_due_jobs()-equivalent logic directly
rather than waiting on a real background thread's poll interval.

Stage 18 task 5: hardened for running this same process on MULTIPLE
backend instances at once (the realistic production shape — several
replicas behind a load balancer, each starting its own scheduler thread
identically). backend.monitoring.lease adds a database-backed lease so
only the current lease-holder instance actually scans for due jobs each
poll iteration; every other instance's poll is a cheap no-op (a single
failed lease-acquire attempt) rather than a full due-config scan. This is
layered ON TOP of, not instead of, run_monitoring_job's own per-job
Postgres advisory lock — that lock is what actually guarantees a due job
never executes twice even if this lease had a bug; the lease exists to
stop the wasted redundant polling and to make "which instance is
leading" observable (see backend.app.routers.ops's health endpoint).
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from collections.abc import Callable

from sqlalchemy.engine import Engine

from backend.core.adapter import DomainAdapter
from backend.monitoring.lease import release_lease, try_acquire_or_renew_lease
from backend.monitoring.service import list_due_configs, run_monitoring_job

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 30
SCHEDULER_LEASE_KEY = "monitoring_scheduler"


def _default_holder_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


class MonitoringScheduler:
    def __init__(
        self,
        engine: Engine,
        adapter_factory: Callable[[str, str], DomainAdapter],
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        holder_id: str | None = None,
    ):
        self._engine = engine
        self._adapter_factory = adapter_factory
        self._poll_interval = poll_interval_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # A lease TTL of 3x the poll interval gives this instance two full
        # missed renewals of slack (transient slowness, a GC pause) before
        # another instance would ever consider the lease lapsed and take
        # over -- avoids lease "flapping" between instances under normal
        # jitter while still reclaiming promptly if this instance actually
        # goes away.
        self._holder_id = holder_id or _default_holder_id()
        self._lease_ttl_seconds = poll_interval_seconds * 3

    def run_due_jobs(self) -> int:
        """Runs every currently-due config once, synchronously — WITHOUT
        acquiring the scheduler lease first. Returns how many were run.
        The one thing a test calls directly instead of waiting on the
        background thread's poll interval; a test invoking this directly
        is deliberately exercising the job logic itself, independent of
        which instance "owns" the lease at that moment."""
        due = list_due_configs(self._engine)
        for config in due:
            try:
                run_monitoring_job(self._engine, config, self._adapter_factory)
            except Exception:
                logger.exception("monitoring job failed for config %s", config.config_id)
        return len(due)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if try_acquire_or_renew_lease(self._engine, SCHEDULER_LEASE_KEY, self._holder_id, self._lease_ttl_seconds):
                    self.run_due_jobs()
            except Exception:
                logger.exception("monitoring scheduler poll iteration failed")
            self._stop_event.wait(self._poll_interval)
        release_lease(self._engine, SCHEDULER_LEASE_KEY, self._holder_id)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="monitoring-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


def scheduler_enabled_via_env() -> bool:
    return os.environ.get("AIPI_MONITORING_SCHEDULER", "0") == "1"
