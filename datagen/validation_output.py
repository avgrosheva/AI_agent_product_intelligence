"""Writes validation_ground_truth.parquet (DATA_MODEL.md SS8).

This is the ONLY place planted-effect ground truth is persisted. It is
written to its own output directory and datagen/load_to_postgres.py never
reads from that directory — the isolation is structural, not a filter
applied at load time.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_validation_ground_truth(out_dir: Path, ground_truth_rows: list[dict]) -> None:
    df = pd.DataFrame(ground_truth_rows)
    df["session_id"] = df["session_id"].astype(str)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "validation_ground_truth.parquet", index=False)
