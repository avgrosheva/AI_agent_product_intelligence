"""Generate the `products` catalog (DATA_MODEL.md SS3.2)."""

from __future__ import annotations

import numpy as np

from datagen.constants import BRANDS, CPU_TIERS, GPU_TIERS, USE_CASE_TAGS
from datagen.ids import entity_id
from datagen.rng import weighted_choice


def _sample_use_case_tags(rng: np.random.Generator, k_choices: tuple[int, int] = (1, 2)) -> list[str]:
    k = int(rng.integers(k_choices[0], k_choices[1] + 1))
    idx = rng.choice(len(USE_CASE_TAGS), size=k, replace=False)
    return sorted(USE_CASE_TAGS[i] for i in idx)


def _laptop_row(rng: np.random.Generator, product_id) -> dict:
    ram_gb = weighted_choice(rng, [8, 16, 32, 64], [0.30, 0.40, 0.22, 0.08])
    storage_gb = weighted_choice(rng, [256, 512, 1024, 2048], [0.25, 0.40, 0.25, 0.10])
    weight_kg = round(float(rng.uniform(0.9, 3.2)), 2)
    cpu_tier = weighted_choice(rng, CPU_TIERS, [0.35, 0.45, 0.20])
    gpu_tier = weighted_choice(rng, GPU_TIERS, [0.45, 0.35, 0.20])
    screen_in = round(float(rng.uniform(13.0, 17.0)), 1)
    base_price = 22000 + ram_gb * 900 + storage_gb * 12 + weight_kg * -3000
    price_noise = float(rng.lognormal(mean=0.0, sigma=0.25))
    price_rub = int(max(25000, min(260000, base_price * price_noise)))
    return {
        "product_id": product_id,
        "category": "laptop",
        "brand": weighted_choice(rng, BRANDS, [1.0] * len(BRANDS)),
        "price_rub": price_rub,
        "ram_gb": ram_gb,
        "storage_gb": storage_gb,
        "weight_kg": weight_kg,
        "cpu_tier": cpu_tier,
        "gpu_tier": gpu_tier,
        "screen_in": screen_in,
        "use_case_tags": _sample_use_case_tags(rng),
        "rating": round(float(rng.beta(6, 2) * 2 + 3), 2),
        "margin_pct": round(float(rng.uniform(0.08, 0.25)), 3),
        "in_stock": bool(rng.random() < 0.92),
    }


def _monitor_row(rng: np.random.Generator, product_id) -> dict:
    screen_in = round(float(rng.uniform(21.0, 34.0)), 1)
    base_price = 12000 + (screen_in - 21) * 1400
    price_noise = float(rng.lognormal(mean=0.0, sigma=0.22))
    price_rub = int(max(9000, min(120000, base_price * price_noise)))
    return {
        "product_id": product_id,
        "category": "monitor",
        "brand": weighted_choice(rng, BRANDS, [1.0] * len(BRANDS)),
        "price_rub": price_rub,
        "ram_gb": None,
        "storage_gb": None,
        "weight_kg": None,
        "cpu_tier": None,
        "gpu_tier": None,
        "screen_in": screen_in,
        "use_case_tags": _sample_use_case_tags(rng),
        "rating": round(float(rng.beta(6, 2) * 2 + 3), 2),
        "margin_pct": round(float(rng.uniform(0.10, 0.22)), 3),
        "in_stock": bool(rng.random() < 0.92),
    }


def _accessory_row(rng: np.random.Generator, product_id) -> dict:
    base_price = float(rng.lognormal(mean=8.2, sigma=0.6))
    price_rub = int(max(500, min(25000, base_price)))
    return {
        "product_id": product_id,
        "category": "accessory",
        "brand": weighted_choice(rng, BRANDS, [1.0] * len(BRANDS)),
        "price_rub": price_rub,
        "ram_gb": None,
        "storage_gb": None,
        "weight_kg": None,
        "cpu_tier": None,
        "gpu_tier": None,
        "screen_in": None,
        "use_case_tags": _sample_use_case_tags(rng, k_choices=(1, 1)),
        "rating": round(float(rng.beta(6, 2) * 2 + 3), 2),
        "margin_pct": round(float(rng.uniform(0.15, 0.35)), 3),
        "in_stock": bool(rng.random() < 0.95),
    }


def generate_products(
    rng: np.random.Generator,
    profile_name: str,
    seed: int,
    n_laptop: int,
    n_monitor: int,
    n_accessory: int,
) -> list[dict]:
    rows = []
    idx = 0
    for _ in range(n_laptop):
        product_id = entity_id(profile_name, seed, "product", idx)
        rows.append(_laptop_row(rng, product_id))
        idx += 1
    for _ in range(n_monitor):
        product_id = entity_id(profile_name, seed, "product", idx)
        rows.append(_monitor_row(rng, product_id))
        idx += 1
    for _ in range(n_accessory):
        product_id = entity_id(profile_name, seed, "product", idx)
        rows.append(_accessory_row(rng, product_id))
        idx += 1
    return rows
