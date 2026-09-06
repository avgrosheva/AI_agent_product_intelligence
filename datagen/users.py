"""Generate the `users` table (DATA_MODEL.md SS3.1)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from datagen.constants import LOCALE_WEIGHTS, LOCALES, PERSONA_WEIGHTS, PERSONAS, PLATFORM_WEIGHTS, PLATFORMS
from datagen.ids import entity_id
from datagen.rng import weighted_choice


def generate_users(
    rng: np.random.Generator, profile_name: str, seed: int, n_users: int, experiment_start: date
) -> list[dict]:
    rows = []
    for i in range(n_users):
        user_id = entity_id(profile_name, seed, "user", i)
        persona = weighted_choice(rng, PERSONAS, PERSONA_WEIGHTS)
        platform_pref = weighted_choice(rng, PLATFORMS, PLATFORM_WEIGHTS)
        locale = weighted_choice(rng, LOCALES, LOCALE_WEIGHTS)
        days_before = int(rng.integers(0, 365))
        signup_date = experiment_start - timedelta(days=days_before)
        rows.append(
            {
                "user_id": user_id,
                "signup_date": signup_date,
                "platform_pref": platform_pref,
                "locale": locale,
                "persona": persona,
            }
        )
    return rows
