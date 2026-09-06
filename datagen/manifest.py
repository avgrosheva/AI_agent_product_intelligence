"""Writes generation_manifest.json (DATA_MODEL.md SS7)."""

from __future__ import annotations

import json
from pathlib import Path

from datagen.constants import EFFECT_PARAMS


def write_manifest(out_dir: Path, profile_name: str, seed: int, row_counts: dict[str, int]) -> None:
    manifest = {
        "profile": profile_name,
        "seed": seed,
        "row_counts": row_counts,
        "planted_effects": EFFECT_PARAMS,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "generation_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
