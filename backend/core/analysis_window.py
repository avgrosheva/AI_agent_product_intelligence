"""Stage 13 task 2: the one consistent analysis-window rule, defined
once and used everywhere a windowed evaluation needs to decide which
sessions count. A session is IN the window when:

    started_at >= window.start   AND   started_at <= window.end

(inclusive on both ends — a session starting exactly at the boundary is
included, never silently dropped). `window.end` is always the
evaluation time; `window.start = window.end - window_hours`.

This is a plain, domain-agnostic value object: it carries no SQL, no
pandas, no knowledge of any adapter. backend.core.adapter.DomainAdapter
implementations decide HOW to apply it to their own storage (Stage 13
task 3: never commerce/support-specific filtering logic living in
backend.monitoring.service).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AnalysisWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"AnalysisWindow.start ({self.start}) must not be after end ({self.end})")

    def contains(self, timestamp: datetime) -> bool:
        return self.start <= timestamp <= self.end
