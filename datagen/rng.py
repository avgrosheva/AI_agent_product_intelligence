"""Seeded RNG helpers.

Every call site receives an explicit `numpy.random.Generator` instance
(created once in generate.py from `--seed`) rather than touching global
random state, per DATA_MODEL.md SS7. Helper functions here are thin,
deterministic wrappers so call sites read like "roll for X" rather than
raw numpy calls.
"""

from __future__ import annotations

import numpy as np


def weighted_choice(rng: np.random.Generator, options: list, weights: list[float]):
    """Deterministic categorical draw given an explicit weight vector."""
    weights_arr = np.asarray(weights, dtype=float)
    weights_arr = weights_arr / weights_arr.sum()
    idx = rng.choice(len(options), p=weights_arr)
    return options[idx]


def bernoulli(rng: np.random.Generator, p: float) -> bool:
    p = min(max(p, 0.0), 1.0)
    return bool(rng.random() < p)


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
