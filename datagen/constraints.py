"""Build per-session constraints_json and check product/constraint satisfaction.

Constraint values are drawn from percentiles of the *actual* catalog
distribution for the session's category (not arbitrary numbers), so a
plausible fraction of the catalog can satisfy them — avoiding the
"obviously artificial separation" the approved docs warn against.
"""

from __future__ import annotations

import numpy as np

from datagen.constants import CONSTRAINT_KEYS_BY_CATEGORY, USE_CASE_TAGS
from datagen.rng import weighted_choice


class CatalogStats:
    """Per-category summary of the generated catalog, used to pick realistic
    constraint thresholds. Built once per run from the generated products.
    """

    def __init__(self, products: list[dict]):
        self._by_category: dict[str, list[dict]] = {}
        for p in products:
            self._by_category.setdefault(p["category"], []).append(p)

    def price_percentile(self, category: str, q: float) -> int:
        prices = [p["price_rub"] for p in self._by_category[category]]
        return int(np.percentile(prices, q))

    def ram_values(self, category: str) -> list[int]:
        return sorted({p["ram_gb"] for p in self._by_category[category] if p["ram_gb"] is not None})

    def weight_percentile(self, category: str, q: float) -> float:
        weights = [p["weight_kg"] for p in self._by_category[category] if p["weight_kg"] is not None]
        return float(np.percentile(weights, q))

    def screen_percentile(self, category: str, q: float) -> float:
        screens = [p["screen_in"] for p in self._by_category[category] if p["screen_in"] is not None]
        return float(np.percentile(screens, q))

    def brands(self, category: str) -> list[str]:
        return sorted({p["brand"] for p in self._by_category[category]})


_PERSONA_BUDGET_PERCENTILE_RANGE = {
    "budget": (20, 55),
    "mainstream": (35, 75),
    "power_user": (55, 95),
    "gift_buyer": (45, 90),
}


def build_constraints(
    rng: np.random.Generator,
    category: str,
    num_constraints: int,
    persona: str,
    stats: CatalogStats,
) -> dict:
    """Return a dict of {constraint_key: value}. Fewer keys than requested
    when the category's pool is smaller than num_constraints (e.g.
    accessory only supports 3 keys).
    """
    pool = CONSTRAINT_KEYS_BY_CATEGORY[category]
    k = min(num_constraints, len(pool))
    if k <= 0:
        return {}
    chosen_idx = rng.choice(len(pool), size=k, replace=False)
    keys = [pool[i] for i in sorted(chosen_idx)]

    constraints: dict = {}
    for key in keys:
        if key == "budget":
            lo, hi = _PERSONA_BUDGET_PERCENTILE_RANGE.get(persona, (30, 80))
            q = float(rng.uniform(lo, hi))
            constraints["budget"] = stats.price_percentile(category, q)
        elif key == "ram_min":
            ram_values = stats.ram_values(category)
            constraints["ram_min"] = int(weighted_choice(rng, ram_values, [1.0] * len(ram_values)))
        elif key == "weight_max":
            q = float(rng.uniform(40, 85))
            constraints["weight_max"] = round(stats.weight_percentile(category, q), 2)
        elif key == "screen_size_min":
            q = float(rng.uniform(15, 70))
            constraints["screen_size_min"] = round(stats.screen_percentile(category, q), 1)
        elif key == "use_case":
            constraints["use_case"] = str(weighted_choice(rng, USE_CASE_TAGS, [1.0] * len(USE_CASE_TAGS)))
        elif key == "brand":
            brands = stats.brands(category)
            constraints["brand"] = str(weighted_choice(rng, brands, [1.0] * len(brands)))
    return constraints


def product_satisfies(product: dict, constraints: dict) -> bool:
    for key, value in constraints.items():
        if key == "budget" and not (product["price_rub"] <= value):
            return False
        if key == "ram_min" and not (product["ram_gb"] is not None and product["ram_gb"] >= value):
            return False
        if key == "weight_max" and not (product["weight_kg"] is not None and product["weight_kg"] <= value):
            return False
        if key == "screen_size_min" and not (
            product["screen_in"] is not None and product["screen_in"] >= value
        ):
            return False
        if key == "use_case" and value not in product["use_case_tags"]:
            return False
        if key == "brand" and product["brand"] != value:
            return False
    return True


def count_satisfied(product: dict, constraints: dict) -> int:
    return sum(1 for key, value in constraints.items() if product_satisfies(product, {key: value}))


def violated_keys(product: dict, constraints: dict) -> list[str]:
    violated = []
    for key in constraints:
        if not product_satisfies(product, {key: constraints[key]}):
            violated.append(key)
    return violated
