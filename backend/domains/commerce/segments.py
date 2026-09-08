"""The commerce domain's pre-treatment segment dimensions and values
(INVESTIGATION.md SS1). backend.investigation.segments.build_segment_registry
is the generic mechanism (single + curated-pairwise segment construction,
sourced from whichever dimensions are registered semantic_class=
"pre_treatment" in the metric registry); this module is the data a
non-shopping domain would replace to segment on its own dimensions."""

from __future__ import annotations

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
