"""Benjamini-Hochberg FDR correction (STATISTICS.md SS6).

Not exercised by any Stage 2 analysis (Stage 2's five effect checks and
metric table are pre-registered comparisons, not an automated multi-segment
scan — that scan is Stage 3's Investigation engine). Implemented and
unit-tested now because ROADMAP.md Stage 2 lists it as part of the shared
stats package, so it is available, correct, and tested before Stage 3
needs it.
"""

from __future__ import annotations

import numpy as np


def benjamini_hochberg(p_values: list[float], q: float = 0.10) -> list[bool]:
    """Return, for each input p-value in its original order, whether it is
    rejected (significant) under the BH procedure at FDR level q.
    """
    p = np.asarray(p_values, dtype=float)
    m = len(p)
    if m == 0:
        return []
    order = np.argsort(p)
    ranked = p[order]
    thresholds = (np.arange(1, m + 1) / m) * q
    below = ranked <= thresholds

    reject_sorted = np.zeros(m, dtype=bool)
    if below.any():
        max_i = int(np.max(np.where(below)[0]))
        reject_sorted[: max_i + 1] = True

    reject = np.zeros(m, dtype=bool)
    reject[order] = reject_sorted
    return reject.tolist()
