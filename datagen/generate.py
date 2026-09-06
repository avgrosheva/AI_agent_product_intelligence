"""CLI entry point: python -m datagen.generate --profile dev --seed 42

Generation order is fixed (DATA_MODEL.md SS7): users -> products ->
experiments -> sessions (and everything nested inside a session) ->
manifest -> validation ground truth. A single numpy.random.Generator,
created once from --seed, is threaded explicitly through every step in
that order, so the same (profile, seed) pair always produces identical
output.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from datagen.constraints import CatalogStats
from datagen.experiments import generate_experiments
from datagen.products import generate_products
from datagen.profiles import get_profile
from datagen.session_builder import build_session
from datagen.users import generate_users

APP_TABLES_EMPTY_SCHEMA = {
    "failure_labels": ["label_id", "session_id", "failure_mode", "confidence", "source", "evidence_text", "created_at"],
}

# Parquet/pyarrow cannot infer a struct type from dicts with heterogeneous
# keys (constraints_json varies row to row), so these columns are stored as
# JSON strings in the application parquet files and parsed back to dicts by
# the loader immediately before insert.
JSON_STRING_COLUMNS = {
    "sessions": ["constraints_json"],
    "tool_calls": ["input_json", "output_json"],
}


def _uuid_columns_to_str(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if len(df) and isinstance(df[col].iloc[0], uuid.UUID):
            df[col] = df[col].astype(str)
    return df


def _json_columns_to_str(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    for col in JSON_STRING_COLUMNS.get(table_name, []):
        if col in df.columns:
            df[col] = df[col].apply(json.dumps)
    return df


def _sessions_per_user(rng: np.random.Generator) -> int:
    return max(1, min(8, int(rng.poisson(2.6)) + 1))


def _random_session_start(rng: np.random.Generator, start: date, days: int) -> datetime:
    day_offset = int(rng.integers(0, days))
    seconds_offset = int(rng.integers(0, 24 * 3600))
    return datetime(start.year, start.month, start.day) + timedelta(days=day_offset, seconds=seconds_offset)


def generate_dataset(profile_name: str, seed: int, out_root: Path) -> dict[str, int]:
    profile = get_profile(profile_name)
    rng = np.random.default_rng(seed)

    t0 = time.time()
    users = generate_users(rng, profile_name, seed, profile.n_users, date.fromisoformat(profile.experiment_start))
    products = generate_products(
        rng,
        profile_name,
        seed,
        profile.n_products_laptop,
        profile.n_products_monitor,
        profile.n_products_accessory,
    )
    experiments = generate_experiments(
        profile_name,
        seed,
        profile.experiment_name,
        date.fromisoformat(profile.experiment_start),
        profile.experiment_days,
    )
    experiment = experiments[0]

    stats = CatalogStats(products)
    products_by_category: dict[str, list[dict]] = {}
    for p in products:
        products_by_category.setdefault(p["category"], []).append(p)

    sessions, messages, agent_actions, tool_calls = [], [], [], []
    recommendations, product_events, evaluations, ground_truth = [], [], [], []

    session_index = 0
    for user in users:
        n_sessions = _sessions_per_user(rng)
        for _ in range(n_sessions):
            session_start = _random_session_start(rng, date.fromisoformat(profile.experiment_start), profile.experiment_days)
            result = build_session(
                rng, profile_name, seed, session_index, user, experiment, products_by_category, stats, session_start
            )
            sessions.append(result.session)
            messages.extend(result.messages)
            agent_actions.extend(result.agent_actions)
            tool_calls.extend(result.tool_calls)
            recommendations.extend(result.recommendations)
            product_events.extend(result.product_events)
            evaluations.extend(result.evaluations)
            ground_truth.append(result.ground_truth)
            session_index += 1

    elapsed = time.time() - t0

    app_dir = out_root / profile_name / "application"
    app_dir.mkdir(parents=True, exist_ok=True)

    def _save(name: str, rows: list[dict], columns: list[str] | None = None) -> int:
        df = pd.DataFrame(rows, columns=columns) if rows or columns else pd.DataFrame(rows)
        df = _uuid_columns_to_str(df)
        df = _json_columns_to_str(df, name)
        df.to_parquet(app_dir / f"{name}.parquet", index=False)
        return len(df)

    row_counts = {
        "users": _save("users", users),
        "products": _save("products", products),
        "experiments": _save("experiments", experiments),
        "sessions": _save("sessions", sessions),
        "messages": _save("messages", messages),
        "agent_actions": _save("agent_actions", agent_actions),
        "tool_calls": _save("tool_calls", tool_calls),
        "recommendations": _save("recommendations", recommendations),
        "product_events": _save("product_events", product_events),
        "evaluations": _save("evaluations", evaluations),
        "failure_labels": _save("failure_labels", [], APP_TABLES_EMPTY_SCHEMA["failure_labels"]),
    }

    from datagen.manifest import write_manifest
    from datagen.validation_output import write_validation_ground_truth

    write_manifest(out_root / profile_name, profile_name, seed, row_counts)
    write_validation_ground_truth(out_root / profile_name, ground_truth)

    print(f"[datagen] profile={profile_name} seed={seed} generated in {elapsed:.1f}s", file=sys.stderr)
    for name, count in row_counts.items():
        print(f"  {name}: {count}", file=sys.stderr)

    return row_counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic conversational-commerce telemetry.")
    parser.add_argument("--profile", choices=["dev", "demo"], required=True)
    parser.add_argument("--seed", type=int, default=None, help="Defaults to the profile's default_seed.")
    parser.add_argument("--out-dir", type=str, default="data")
    args = parser.parse_args()

    profile = get_profile(args.profile)
    seed = args.seed if args.seed is not None else profile.default_seed
    generate_dataset(args.profile, seed, Path(args.out_dir))


if __name__ == "__main__":
    main()
