"""Dataset profile configuration (DATA_MODEL.md SS5).

Sizes match the dev/demo targets in DATA_MODEL.md SS5. Product catalog
split is 60% laptop / 23.3% monitor / 16.7% accessory in both profiles.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    default_seed: int
    n_users: int
    n_products_laptop: int
    n_products_monitor: int
    n_products_accessory: int
    experiment_name: str
    experiment_start: str  # ISO date
    experiment_days: int

    @property
    def n_products(self) -> int:
        return self.n_products_laptop + self.n_products_monitor + self.n_products_accessory


DEV = Profile(
    name="dev",
    default_seed=42,
    n_users=600,
    n_products_laptop=90,
    n_products_monitor=35,
    n_products_accessory=25,
    experiment_name="Clarification Policy v2",
    experiment_start="2026-01-05",
    experiment_days=28,
)

DEMO = Profile(
    name="demo",
    default_seed=2024,
    n_users=9000,
    n_products_laptop=240,
    n_products_monitor=90,
    n_products_accessory=70,
    experiment_name="Clarification Policy v2",
    experiment_start="2026-01-05",
    experiment_days=28,
)

PROFILES = {"dev": DEV, "demo": DEMO}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown profile '{name}'; choose one of {sorted(PROFILES)}") from exc
