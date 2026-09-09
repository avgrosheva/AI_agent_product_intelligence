"""Stage 4 commerce regression: the commerce domain's own segment
dimensions/allowlist, as exposed through CommerceAdapter's
InvestigationConfig, still build the exact same bounded segment lattice
as before build_segment_registry() took its dimension data as explicit
arguments instead of importing backend.domains.commerce.segments
directly. Pure data — no database needed."""

from __future__ import annotations

import pandas as pd

from backend.domains.commerce.investigation_config import commerce_investigation_config
from backend.domains.commerce.segments import DIMENSION_VALUES, PAIRWISE_ALLOWLIST
from backend.investigation.segments import build_segment_registry

_CONFIG = commerce_investigation_config()

POST_TREATMENT_NAMES = {
    "trajectory_pattern", "has_clarify_action", "tool_call_count",
    "session_latency_ms", "recommendation_properties",
}


def test_commerce_pre_treatment_dimensions_match_the_shared_registrys_pre_treatment_class():
    assert set(_CONFIG.pre_treatment_dimensions) == {
        "requested_category", "constraint_count_bucket", "platform", "device_tier", "locale", "persona",
    }


def test_no_post_treatment_variable_is_ever_a_commerce_segment_dimension():
    dims = set(_CONFIG.pre_treatment_dimensions)
    assert dims.isdisjoint(POST_TREATMENT_NAMES)
    for dim_a, dim_b in _CONFIG.pairwise_allowlist:
        assert dim_a not in POST_TREATMENT_NAMES
        assert dim_b not in POST_TREATMENT_NAMES


def test_commerce_segment_registry_is_bounded():
    segs = build_segment_registry(_CONFIG.dimension_values, _CONFIG.pairwise_allowlist, _CONFIG.pre_treatment_dimensions)
    single_dim_count = sum(len(v) for v in DIMENSION_VALUES.values())
    pairwise_count = sum(len(DIMENSION_VALUES[a]) * len(DIMENSION_VALUES[b]) for a, b in PAIRWISE_ALLOWLIST)
    assert len(segs) == single_dim_count + pairwise_count
    assert len(segs) < 100, "segment lattice should stay bounded, not expand into a general search"


def test_commerce_single_dimension_segments_cover_every_documented_value():
    segs = build_segment_registry(_CONFIG.dimension_values, _CONFIG.pairwise_allowlist, _CONFIG.pre_treatment_dimensions)
    single = [s for s in segs if len(s.dimensions) == 1]
    for dim, values in DIMENSION_VALUES.items():
        labels = {s.label for s in single if s.dimensions == (dim,)}
        assert labels == {f"{dim}={v}" for v in values}


def test_commerce_pairwise_allowlist_is_curated_not_the_full_grid():
    """6 pre-treatment dims -> 15 possible pairs; the allowlist must be a
    small curated subset, not the full combinatorial grid."""
    n_dims = len(_CONFIG.pre_treatment_dimensions)
    full_grid_size = n_dims * (n_dims - 1) // 2
    assert len(PAIRWISE_ALLOWLIST) < full_grid_size


def test_commerce_every_segment_mask_only_touches_registered_dimensions():
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
    for seg in build_segment_registry(_CONFIG.dimension_values, _CONFIG.pairwise_allowlist, _CONFIG.pre_treatment_dimensions):
        mask = seg.mask_fn(df)
        assert isinstance(mask, pd.Series)
        assert mask.dtype == bool
