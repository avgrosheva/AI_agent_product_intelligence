"""Bounded segment lattice over PRE-TREATMENT dimensions only
(INVESTIGATION.md SS1; Stage 2 review requirement #1).

The dimension list is derived directly from
`backend.analytics.metric_registry.pre_treatment_dimensions()` rather than
hard-coded here a second time — this is a structural enforcement, not a
convention: it is impossible for this module to accidentally include a
post-treatment/mechanism variable (clarification, latency, trajectories,
tool calls, recommendation properties) as a segmentation dimension without
also mis-registering it as `semantic_class="pre_treatment"` in the shared
registry, which is covered by its own tests
(tests/test_experiment_results.py, tests/test_investigation_segments.py).

Single-dimension scan: every value of every pre-treatment dimension.
Pairwise scan: only the curated allowlist below (INVESTIGATION.md SS1) —
not the full combinatorial grid — to keep the test count bounded and every
surfaced segment explainable in one sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from backend.analytics import metric_registry

DIMENSION_VALUES: dict[str, list[str]] = {
    "requested_category": ["laptop", "monitor", "accessory"],
    "constraint_count_bucket": ["0-1", "2", "3+"],
    "platform": ["web", "ios", "android"],
    "device_tier": ["low", "mid", "high"],
    "locale": ["ru-RU", "en-US"],
    "persona": ["budget", "mainstream", "power_user", "gift_buyer"],
}

# Pairwise allowlist (INVESTIGATION.md SS1) — curated, not the full grid.
PAIRWISE_ALLOWLIST: list[tuple[str, str]] = [
    ("constraint_count_bucket", "platform"),
    ("constraint_count_bucket", "requested_category"),
    ("platform", "device_tier"),
    ("constraint_count_bucket", "persona"),
]


def registered_pre_treatment_dimensions() -> list[str]:
    """The only dimensions this module is allowed to segment on — sourced
    from the shared registry's semantic_class, not redeclared here."""
    return [m.name for m in metric_registry.pre_treatment_dimensions()]


@dataclass(frozen=True)
class Segment:
    label: str
    dimensions: tuple[str, ...]
    values: tuple[str, ...]
    mask_fn: Callable[[pd.DataFrame], pd.Series]


def build_segment_registry() -> list[Segment]:
    dims = registered_pre_treatment_dimensions()
    missing = set(dims) - set(DIMENSION_VALUES)
    if missing:
        raise ValueError(f"DIMENSION_VALUES is missing values for registered pre-treatment dimensions: {missing}")

    segments: list[Segment] = []

    for dim in dims:
        for value in DIMENSION_VALUES[dim]:
            segments.append(
                Segment(
                    label=f"{dim}={value}",
                    dimensions=(dim,),
                    values=(value,),
                    mask_fn=(lambda df, d=dim, v=value: df[d] == v),
                )
            )

    for dim_a, dim_b in PAIRWISE_ALLOWLIST:
        if dim_a not in dims or dim_b not in dims:
            raise ValueError(f"Pairwise allowlist references a non-registered dimension: {(dim_a, dim_b)}")
        for va in DIMENSION_VALUES[dim_a]:
            for vb in DIMENSION_VALUES[dim_b]:
                segments.append(
                    Segment(
                        label=f"{dim_a}={va} & {dim_b}={vb}",
                        dimensions=(dim_a, dim_b),
                        values=(va, vb),
                        mask_fn=(lambda df, da=dim_a, va=va, db=dim_b, vb=vb: (df[da] == va) & (df[db] == vb)),
                    )
                )

    return segments
