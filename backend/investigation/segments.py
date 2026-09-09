"""Bounded segment lattice over PRE-TREATMENT dimensions only
(INVESTIGATION.md SS1; Stage 2 review requirement #1).

Stage 4: this module is now the fully generic mechanism only — every
domain-specific input (which dimensions are registered pre_treatment,
their allowed values, and the curated pairwise allowlist) is passed in by
the caller, sourced from the active DomainAdapter
(backend.core.investigation_config.investigation_config_from_adapter), not
imported here. It is structurally impossible for a caller to segment on a
post-treatment/mechanism variable without also mis-declaring it
semantic_class="pre_treatment" in that domain's own metric registry — the
same structural guarantee as before, just no longer anchored to one
hardcoded (commerce) registry.

Single-dimension scan: every value of every pre-treatment dimension.
Pairwise scan: only the caller's curated allowlist — not the full
combinatorial grid — to keep the test count bounded and every surfaced
segment explainable in one sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

__all__ = ["Segment", "build_segment_registry"]


@dataclass(frozen=True)
class Segment:
    label: str
    dimensions: tuple[str, ...]
    values: tuple[str, ...]
    mask_fn: Callable[[pd.DataFrame], pd.Series]


def build_segment_registry(
    dimension_values: dict[str, list[str]],
    pairwise_allowlist: list[tuple[str, str]],
    pre_treatment_dimensions: list[str],
) -> list[Segment]:
    dims = pre_treatment_dimensions
    missing = set(dims) - set(dimension_values)
    if missing:
        raise ValueError(f"dimension_values is missing values for registered pre-treatment dimensions: {missing}")

    segments: list[Segment] = []

    for dim in dims:
        for value in dimension_values[dim]:
            segments.append(
                Segment(
                    label=f"{dim}={value}",
                    dimensions=(dim,),
                    values=(value,),
                    mask_fn=(lambda df, d=dim, v=value: df[d] == v),
                )
            )

    for dim_a, dim_b in pairwise_allowlist:
        if dim_a not in dims or dim_b not in dims:
            raise ValueError(f"Pairwise allowlist references a non-registered dimension: {(dim_a, dim_b)}")
        for va in dimension_values[dim_a]:
            for vb in dimension_values[dim_b]:
                segments.append(
                    Segment(
                        label=f"{dim_a}={va} & {dim_b}={vb}",
                        dimensions=(dim_a, dim_b),
                        values=(va, vb),
                        mask_fn=(lambda df, da=dim_a, va=va, db=dim_b, vb=vb: (df[da] == va) & (df[db] == vb)),
                    )
                )

    return segments
