"""Generate the `experiments` table (DATA_MODEL.md SS3.3)."""

from __future__ import annotations

from datetime import date, timedelta

from datagen.ids import entity_id


def generate_experiments(profile_name: str, seed: int, name: str, start: date, days: int) -> list[dict]:
    experiment_id = entity_id(profile_name, seed, "experiment", 0)
    return [
        {
            "experiment_id": experiment_id,
            "name": name,
            "control_version": "v1",
            "treatment_version": "v2",
            "start_date": start,
            "end_date": start + timedelta(days=days),
            "traffic_split": 0.5,
            "status": "completed",
        }
    ]
