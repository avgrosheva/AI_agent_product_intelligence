"""Thin runner for the .sql files in backend/analytics/sql/.

Deliberately not an ORM query builder: per the Stage 1 review requirement
to keep SQL visible and readable, every analysis in sql/ is a plain,
inspectable .sql file. This module only reads the file and executes it —
it adds no query-construction logic of its own.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

SQL_DIR = Path(__file__).parent / "sql"


def list_sql_files() -> list[str]:
    return sorted(p.name for p in SQL_DIR.glob("*.sql"))


def run_sql_file(engine: Engine, filename: str) -> pd.DataFrame:
    sql_text = (SQL_DIR / filename).read_text(encoding="utf-8")
    with engine.connect() as conn:
        return pd.read_sql(text(sql_text), conn)
