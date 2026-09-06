"""Reproducibility: same (profile, seed) -> byte-identical canonical output.

DATA_MODEL.md SS7: two runs with the same profile and seed must produce
identical canonical outputs. This is the guarantee that makes the whole
dataset trustworthy as a fixed answer key for later stages.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from datagen.generate import generate_dataset

TABLES = [
    "users",
    "products",
    "experiments",
    "sessions",
    "messages",
    "agent_actions",
    "tool_calls",
    "recommendations",
    "product_events",
    "evaluations",
    "failure_labels",
]


def _canonical_hash(df: pd.DataFrame) -> str:
    if df.empty:
        return "empty:" + ",".join(df.columns)
    sort_cols = [c for c in df.columns if c.endswith("_id")] or list(df.columns)
    df_sorted = df.sort_values(sort_cols).reset_index(drop=True)
    csv_bytes = df_sorted.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(csv_bytes).hexdigest()


def test_dev_profile_is_byte_identical_across_two_runs(tmp_path: Path):
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    counts_a = generate_dataset("dev", 42, out_a)
    counts_b = generate_dataset("dev", 42, out_b)

    assert counts_a == counts_b

    for table in TABLES:
        df_a = pd.read_parquet(out_a / "dev" / "application" / f"{table}.parquet")
        df_b = pd.read_parquet(out_b / "dev" / "application" / f"{table}.parquet")
        assert _canonical_hash(df_a) == _canonical_hash(df_b), f"{table} differs between identical-seed runs"

    gt_a = pd.read_parquet(out_a / "dev" / "validation_ground_truth.parquet")
    gt_b = pd.read_parquet(out_b / "dev" / "validation_ground_truth.parquet")
    assert _canonical_hash(gt_a) == _canonical_hash(gt_b)


@pytest.mark.slow
def test_demo_profile_is_byte_identical_across_two_runs(tmp_path: Path):
    """Stage 5 SS2: demo-scale reproducibility, parameterized from the dev
    test above rather than duplicated — marked slow (two full demo
    generations, ~30-60s each) and excluded from the default test run."""
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    counts_a = generate_dataset("demo", 2024, out_a)
    counts_b = generate_dataset("demo", 2024, out_b)

    assert counts_a == counts_b

    for table in TABLES:
        df_a = pd.read_parquet(out_a / "demo" / "application" / f"{table}.parquet")
        df_b = pd.read_parquet(out_b / "demo" / "application" / f"{table}.parquet")
        assert _canonical_hash(df_a) == _canonical_hash(df_b), f"{table} differs between identical-seed demo runs"

    gt_a = pd.read_parquet(out_a / "demo" / "validation_ground_truth.parquet")
    gt_b = pd.read_parquet(out_b / "demo" / "validation_ground_truth.parquet")
    assert _canonical_hash(gt_a) == _canonical_hash(gt_b)


def test_different_seeds_produce_different_output(tmp_path: Path):
    out_a = tmp_path / "seed_42"
    out_b = tmp_path / "seed_43"

    generate_dataset("dev", 42, out_a)
    generate_dataset("dev", 43, out_b)

    sessions_a = pd.read_parquet(out_a / "dev" / "application" / "sessions.parquet")
    sessions_b = pd.read_parquet(out_b / "dev" / "application" / "sessions.parquet")
    assert _canonical_hash(sessions_a) != _canonical_hash(sessions_b)


@pytest.mark.slow
def test_demo_different_seed_produces_different_output(tmp_path: Path):
    out_a = tmp_path / "seed_2024"
    out_b = tmp_path / "seed_2025"

    generate_dataset("demo", 2024, out_a)
    generate_dataset("demo", 2025, out_b)

    sessions_a = pd.read_parquet(out_a / "demo" / "application" / "sessions.parquet")
    sessions_b = pd.read_parquet(out_b / "demo" / "application" / "sessions.parquet")
    assert _canonical_hash(sessions_a) != _canonical_hash(sessions_b)


def test_uuids_are_deterministic_not_from_os_urandom():
    """Guards against the DATA_MODEL.md SS7 warning: uuid4()/os.urandom-based
    ids would silently break reproducibility."""
    from datagen.ids import entity_id

    a = entity_id("dev", 42, "user", 0)
    b = entity_id("dev", 42, "user", 0)
    assert a == b
    c = entity_id("dev", 42, "user", 1)
    assert a != c
