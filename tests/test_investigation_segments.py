"""Bounded segment registry and pre-treatment-only eligibility
(INVESTIGATION.md SS1; Stage 2 review requirement #1)."""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from backend.analytics import metric_registry
from backend.investigation import segments as segments_module
from backend.investigation.segments import (
    DIMENSION_VALUES,
    PAIRWISE_ALLOWLIST,
    build_segment_registry,
    registered_pre_treatment_dimensions,
)

POST_TREATMENT_NAMES = {
    "trajectory_pattern", "has_clarify_action", "tool_call_count",
    "session_latency_ms", "recommendation_properties",
}


def test_registered_dimensions_match_the_shared_registrys_pre_treatment_class():
    dims = set(registered_pre_treatment_dimensions())
    expected = {m.name for m in metric_registry.pre_treatment_dimensions()}
    assert dims == expected
    assert dims == {"requested_category", "constraint_count_bucket", "platform", "device_tier", "locale", "persona"}


def test_no_post_treatment_variable_is_ever_a_segment_dimension():
    dims = set(registered_pre_treatment_dimensions())
    assert dims.isdisjoint(POST_TREATMENT_NAMES)
    for dim_a, dim_b in PAIRWISE_ALLOWLIST:
        assert dim_a not in POST_TREATMENT_NAMES
        assert dim_b not in POST_TREATMENT_NAMES


def test_segment_module_source_never_references_post_treatment_columns():
    """Structural guard: the module's actual segment-building code must
    never mention a mechanism variable, not even as a hard-coded string."""
    source = inspect.getsource(segments_module)
    for forbidden in ["clarify", "latency_ms", "trajectory", "tool_call", "satisfies_constraints", "has_consecutive_search"]:
        assert forbidden not in source, f"segments.py references a post-treatment concept: {forbidden}"


def test_segment_registry_is_bounded():
    segs = build_segment_registry()
    single_dim_count = sum(len(v) for v in DIMENSION_VALUES.values())
    pairwise_count = sum(len(DIMENSION_VALUES[a]) * len(DIMENSION_VALUES[b]) for a, b in PAIRWISE_ALLOWLIST)
    assert len(segs) == single_dim_count + pairwise_count
    assert len(segs) < 100, "segment lattice should stay bounded, not expand into a general search"


def test_every_segment_mask_only_touches_registered_dimensions():
    df = pd.DataFrame(
        {
            "requested_category": ["laptop", "monitor", "accessory"],
            "constraint_count_bucket": ["0-1", "2", "3+"],
            "platform": ["web", "ios", "android"],
            "device_tier": ["low", "mid", "high"],
            "locale": ["ru-RU", "en-US", "ru-RU"],
            "persona": ["budget", "mainstream", "power_user"],
        }
    )
    for seg in build_segment_registry():
        mask = seg.mask_fn(df)
        assert isinstance(mask, pd.Series)
        assert mask.dtype == bool


def test_single_dimension_segments_cover_every_documented_value():
    segs = build_segment_registry()
    single = [s for s in segs if len(s.dimensions) == 1]
    for dim, values in DIMENSION_VALUES.items():
        labels = {s.label for s in single if s.dimensions == (dim,)}
        assert labels == {f"{dim}={v}" for v in values}


def test_pairwise_allowlist_is_curated_not_the_full_grid():
    """6 pre-treatment dims -> 15 possible pairs; the allowlist must be a
    small curated subset, not the full combinatorial grid."""
    n_dims = len(registered_pre_treatment_dimensions())
    full_grid_size = n_dims * (n_dims - 1) // 2
    assert len(PAIRWISE_ALLOWLIST) < full_grid_size


def test_dimension_values_raises_on_missing_registered_dimension(monkeypatch):
    monkeypatch.setattr(segments_module, "DIMENSION_VALUES", {"requested_category": ["laptop"]})
    with pytest.raises(ValueError):
        build_segment_registry()
