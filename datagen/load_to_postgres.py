"""Bulk-load the generated application parquet files into Postgres.

Deliberately reads only from <out_dir>/<profile>/application/ — never
from validation_ground_truth.parquet or generation_manifest.json, which
live one directory up. This is the structural half of the ground-truth
isolation guarantee (DATA_MODEL.md SS8): this script has no code path
that could read the validation artifact even by mistake, because it
never looks in that directory at all.

Insert order follows FK dependencies: users/products/experiments first,
then sessions, then everything that references a session.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, insert, text
from sqlalchemy.orm import Session as OrmSession

from backend.app.db import get_database_url
from backend.app.models import (
    AgentAction,
    Evaluation,
    Experiment,
    FailureLabel,
    Message,
    Product,
    ProductEvent,
    Recommendation,
    Session,
    ToolCall,
    User,
)

# Load order respects FK dependencies.
TABLE_ORDER: list[tuple[str, type]] = [
    ("users", User),
    ("products", Product),
    ("experiments", Experiment),
    ("sessions", Session),
    ("messages", Message),
    ("agent_actions", AgentAction),
    ("tool_calls", ToolCall),
    ("recommendations", Recommendation),
    ("product_events", ProductEvent),
    ("evaluations", Evaluation),
    ("failure_labels", FailureLabel),
]

JSON_STRING_COLUMNS = {
    "sessions": ["constraints_json"],
    "tool_calls": ["input_json", "output_json"],
}


def _rows_from_parquet(app_dir: Path, table_name: str) -> list[dict]:
    df = pd.read_parquet(app_dir / f"{table_name}.parquet")
    for col in JSON_STRING_COLUMNS.get(table_name, []):
        if col in df.columns:
            df[col] = df[col].apply(json.loads)
    # pandas/pyarrow round-trips NaT/NaN for missing optional fields; SQLAlchemy
    # expects Python None for NULL.
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def truncate_all(engine) -> None:
    with engine.begin() as conn:
        table_names = ", ".join(name for name, _ in reversed(TABLE_ORDER))
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


def load_dataset(profile_name: str, data_root: Path, database_url: str | None = None, truncate: bool = True) -> dict[str, int]:
    engine = create_engine(database_url or get_database_url())
    app_dir = data_root / profile_name / "application"

    if truncate:
        truncate_all(engine)

    counts: dict[str, int] = {}
    with OrmSession(engine) as session:
        for table_name, model in TABLE_ORDER:
            rows = _rows_from_parquet(app_dir, table_name)
            if rows:
                session.execute(insert(model), rows)
            counts[table_name] = len(rows)
        session.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Load generated application tables into Postgres.")
    parser.add_argument("--profile", choices=["dev", "demo"], required=True)
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--no-truncate", action="store_true")
    args = parser.parse_args()

    counts = load_dataset(args.profile, Path(args.data_dir), truncate=not args.no_truncate)
    for name, count in counts.items():
        print(f"  {name}: {count} rows loaded")


if __name__ == "__main__":
    main()
