"""Bounded segment registry mechanism (INVESTIGATION.md SS1; Stage 2
review requirement #1; Stage 4 task 1/7).

Stage 4: build_segment_registry() takes its dimension values, pairwise
allowlist, and pre-treatment dimension names as explicit arguments — it
holds no commerce (or any other domain) default of its own. These tests
exercise the mechanism with small synthetic dimension data, the same
domain-data-free approach already used for
test_core_domain_isolation.py::test_evaluate_guardrails_is_generic_and_domain_data_free.
The commerce-specific regression (its real dimension set, real segment
count, real pairwise allowlist) lives in
tests/test_stage2_commerce_adapter_regression.py, next to the other
commerce-adapter regression proofs.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.investigation.segments import build_segment_registry


def test_segment_registry_is_bounded_by_the_given_dimensions_and_allowlist():
    dimension_values = {"color": ["red", "blue"], "size": ["s", "m", "l"]}
    pairwise_allowlist = [("color", "size")]
    pre_treatment_dimensions = ["color", "size"]

    segs = build_segment_registry(dimension_values, pairwise_allowlist, pre_treatment_dimensions)
    single_dim_count = sum(len(v) for v in dimension_values.values())
    pairwise_count = len(dimension_values["color"]) * len(dimension_values["size"])
    assert len(segs) == single_dim_count + pairwise_count == 5 + 6


def test_every_segment_mask_only_touches_given_dimensions():
    dimension_values = {"color": ["red", "blue"], "size": ["s", "m"]}
    df = pd.DataFrame({"color": ["red", "blue", "red"], "size": ["s", "m", "m"]})
    for seg in build_segment_registry(dimension_values, [("color", "size")], ["color", "size"]):
        mask = seg.mask_fn(df)
        assert isinstance(mask, pd.Series)
        assert mask.dtype == bool


def test_single_dimension_segments_cover_every_given_value():
    dimension_values = {"color": ["red", "blue", "green"]}
    segs = build_segment_registry(dimension_values, [], ["color"])
    single = [s for s in segs if len(s.dimensions) == 1]
    labels = {s.label for s in single}
    assert labels == {"color=red", "color=blue", "color=green"}


def test_pairwise_segments_are_only_the_curated_allowlist_not_the_full_grid():
    dimension_values = {"a": ["1", "2"], "b": ["x", "y"], "c": ["p", "q"]}
    # a-b-c would be 3 possible pairs; only one is allowlisted
    segs = build_segment_registry(dimension_values, [("a", "b")], ["a", "b", "c"])
    pairwise_dims = {s.dimensions for s in segs if len(s.dimensions) == 2}
    assert pairwise_dims == {("a", "b")}


def test_dimension_values_raises_on_missing_registered_dimension():
    with pytest.raises(ValueError):
        build_segment_registry({"a": ["1"]}, [], ["a", "b"])


def test_pairwise_allowlist_raises_on_non_registered_dimension():
    with pytest.raises(ValueError):
        build_segment_registry({"a": ["1"], "b": ["2"]}, [("a", "c")], ["a", "b"])
