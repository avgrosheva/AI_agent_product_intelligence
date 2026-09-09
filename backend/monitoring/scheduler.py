"""Stage 11 task 1: "use background jobs, not request-blocking loops."
A lightweight, dependency-free polling thread — proportionate to this
project's scale, matching the existing opt-in-background-work precedent
(backend.app.warmup, gated behind AIPI_WARMUP_ON_STARTUP) rather than
pulling in Celery/RQ/APScheduler for a handful of periodic checks.

Disabled by default (AIPI_MONITORING_SCHEDULER=1 to enable) so normal
dev startup and the test suite are unaffected — tests call
backend.monitoring.service.run_due_jobs()-equivalent logic directly
rather than waiting on a real background thread's poll interval.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable

from sqlalchemy.engine import Engine

from backend.core.adapter import DomainAdapter
from backend.monitoring.service import list_due_configs, run_monitoring_job

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 30


class MonitoringScheduler:
    def __init__(self, engine: Engine, adapter_factory: Callable[[str, str], DomainAdapter], poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS):
        self._engine = engine
        self._adapter_factory = adapter_factory
        self._poll_interval = poll_interval_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def run_due_jobs(self) -> int:
        """Runs every currently-due config once, synchronously. Returns
        how many were run. The one thing a test calls directly instead of
        waiting on the background thread's poll interval."""
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
                self.run_due_jobs()
            except Exception:
                logger.exception("monitoring scheduler poll iteration failed")
            self._stop_event.wait(self._poll_interval)

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
