"""Static generation parameters: distributions, taxonomies, and the five
planted-effect magnitudes (DATA_MODEL.md SS6). Centralized here so
generation_manifest.json can record the exact numbers actually used,
and so effects.py / session_builder.py never hard-code a magnitude inline.
"""

BRANDS = [
    "Nordkap", "Velatek", "Orionis", "Kestrel", "Marrow",
    "Solventa", "Iridian", "Kobalt", "Fennix", "Halcyon",
    "Perigee", "Vantor",
]

USE_CASE_TAGS = ["programming", "gaming", "office", "content_creation"]

CATEGORIES = ["laptop", "monitor", "accessory"]

# Session-level requested-category demand mix (distinct from the catalog mix
# in profiles.py; realistic that demand doesn't exactly match supply).
REQUEST_CATEGORY_WEIGHTS = {"laptop": 0.60, "monitor": 0.25, "accessory": 0.15}

PERSONAS = ["budget", "mainstream", "power_user", "gift_buyer"]
PERSONA_WEIGHTS = [0.30, 0.40, 0.20, 0.10]

PLATFORMS = ["web", "ios", "android"]
PLATFORM_WEIGHTS = [0.50, 0.25, 0.25]

DEVICE_TIERS = ["low", "mid", "high"]
DEVICE_TIER_WEIGHTS = [0.30, 0.50, 0.20]

LOCALES = ["ru-RU", "en-US"]
LOCALE_WEIGHTS = [0.85, 0.15]

CPU_TIERS = ["entry", "mid", "high"]
GPU_TIERS = ["integrated", "entry_discrete", "high_discrete"]

# Per-category constraint key pools. Every key maps to an existing product
# column (DATA_MODEL.md SS3.2) — no schema columns are invented to support
# a planted effect (see PRD.md deviations note for effect #4).
CONSTRAINT_KEYS_BY_CATEGORY = {
    "laptop": ["budget", "ram_min", "weight_max", "use_case", "brand"],
    "monitor": ["budget", "screen_size_min", "use_case", "brand"],
    "accessory": ["budget", "use_case", "brand"],
}

# num_constraints distribution (baseline, before persona modulation).
NUM_CONSTRAINTS_VALUES = [0, 1, 2, 3, 4, 5]
NUM_CONSTRAINTS_WEIGHTS = [0.15, 0.25, 0.25, 0.20, 0.10, 0.05]

# Trajectory templates and their baseline probability by constraint bucket
# ("0-1", "2", "3+"). Effects shift these (datagen/effects.py) before the
# categorical draw — see session_builder.py.
TRAJECTORY_TEMPLATES = [
    "simple_success",
    "filtered_success",
    "clarified_success",
    "redundant_search_success",
    "dead_end_abandon",
    "clarify_then_abandon",
]

BASELINE_TEMPLATE_WEIGHTS = {
    "0-1": {
        "simple_success": 0.30,
        "filtered_success": 0.15,
        "clarified_success": 0.35,
        "redundant_search_success": 0.10,
        "dead_end_abandon": 0.07,
        "clarify_then_abandon": 0.03,
    },
    "2": {
        "simple_success": 0.30,
        "filtered_success": 0.30,
        "clarified_success": 0.15,
        "redundant_search_success": 0.12,
        "dead_end_abandon": 0.08,
        "clarify_then_abandon": 0.05,
    },
    "3+": {
        "simple_success": 0.28,
        "filtered_success": 0.40,
        "clarified_success": 0.08,
        "redundant_search_success": 0.10,
        "dead_end_abandon": 0.08,
        "clarify_then_abandon": 0.06,
    },
}


def constraint_bucket(num_constraints: int) -> str:
    if num_constraints <= 1:
        return "0-1"
    if num_constraints == 2:
        return "2"
    return "3+"


# ---------------------------------------------------------------------------
# Planted effect magnitudes (DATA_MODEL.md SS6). Kept as named constants so
# generation_manifest.json can echo the exact values used for a given run.
# ---------------------------------------------------------------------------

BASELINE_VIOLATION_RATE = 0.03  # background, version-independent "agent picked an imperfect match" noise

# LLM token pricing (METRICS.md SS6). Illustrative, versioned constants —
# not tied to a specific real vendor price list.
PRICE_IN_PER_1K_TOKENS = 0.003
PRICE_OUT_PER_1K_TOKENS = 0.015

EFFECT_PARAMS = {
    "exploratory_uplift": {
        "target_segment": "constraint_count_bucket=0-1",
        "direction": "v2_better",
        # at num_constraints==1 (the only non-vacuous case in this bucket), chance the agent's
        # selection violates the single stated constraint even though a matching product exists
        "violation_rate_v1": 0.15,
        "violation_rate_v2": 0.05,
        # small shift of template mass from abandon templates to success templates for v2
        "template_shift_to_success": 0.05,
    },
    "overclarify_v2": {
        "target_segment": "constraint_count_bucket=3+",
        "direction": "v2_worse",
        # probability mass added to clarified_success + clarify_then_abandon for v2, 3+ bucket
        "clarify_prob_boost": 0.30,
        "clarify_then_abandon_boost": 0.08,
    },
    "android_latency": {
        "target_segment": "platform=android",
        "direction": "v2_worse",
        "search_latency_extra_ms_mean": 550,
        "search_latency_extra_ms_sd": 120,
        # calibrated against the observed total_latency_ms distribution (baseline
        # mean ~1400ms, android+v2 mean ~2200ms): midpoint sits at the elevated
        # segment's mean so baseline sessions land on the low tail of the curve
        # (~5% abandon-from-latency) while android+v2 sessions land mid-curve
        # (~30%), giving a real dose-response rather than an inert threshold.
        "abandon_logistic_midpoint_ms": 2200,
        "abandon_logistic_scale_ms": 350,
        "abandon_logistic_max_prob": 0.60,
    },
    "monitor_constraint_regression_v2": {
        "target_segment": "requested_category=monitor",
        "direction": "v2_worse",
        "violation_rate_v1": 0.08,
        "violation_rate_v2": 0.22,
    },
    "tool_selection_v2_improved": {
        "target_segment": "all",
        "direction": "v2_better",
        "redundant_search_relative_reduction_v2": 0.40,
    },
}
