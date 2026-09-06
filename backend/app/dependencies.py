"""Shared FastAPI dependencies.

Stage 4 review note: at dev-dataset scale every query here ran in well
under a second, so no caching was added then. Stage 5 measured demo-scale
response times of 24-27s on /metrics and /investigation, driven by
re-running the same deterministic query/computation on every request; the
dataframes below are cached for the process lifetime (in-process
lru_cache, not a new caching service) since Stage 4 established there is
no write path that mutates sessions/agent_actions/failure_labels after
load. A future stage that adds live mutation would need to invalidate
these.

Cache lifecycle: every cache here (and the metric-table/investigation
caches in routers.experiments/routers.investigation) lives only for the
current process and the dataset that was loaded when it started. There is
no invalidation hook. If the underlying data changes — a fresh
datagen.load_to_postgres run, switching profiles, reclassification — the
server process must be restarted; see backend.app.warmup for the optional
startup warm-up that repopulates these caches eagerly for a demo deploy.
"""

from __future__ import annotations

import uuid
from functools import lru_cache

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.app.db import get_database_url
from backend.analytics.sql_runner import run_sql_file


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(get_database_url())


@lru_cache(maxsize=1)
def _get_full_base_df_cached() -> pd.DataFrame:
    """Session-level base query result, cached for the process lifetime.
    Safe because Stage 4 has no write path that changes sessions/messages/
    etc. after load — a future stage that adds live mutation would need to
    invalidate this."""
    return run_sql_file(get_engine(), "session_level_base.sql")


def get_base_df(experiment_id: str | None = None) -> pd.DataFrame:
    """Every router that operates on "this experiment's data" must pass
    experiment_id explicitly — session_level_base.sql spans every
    experiment in the database, and the dev dataset's single experiment
    made that easy to get away with omitting until the demo dataset (with
    2 experiments, DATA_MODEL.md SS5) would have silently mixed them."""
    df = _get_full_base_df_cached()
    if experiment_id is None:
        return df
    return df[df["experiment_id"].astype(str) == experiment_id]


@lru_cache(maxsize=1)
def get_agent_actions_df() -> pd.DataFrame:
    """Cached for the process lifetime, same rationale as
    _get_full_base_df_cached (Stage 5 SS13: this table is read fresh on
    every investigation call, and at demo scale that query plus the
    downstream computation was the dominant cost of a 24s+ response)."""
    with get_engine().connect() as conn:
        return pd.read_sql(
            text("SELECT session_id, sequence_index, action_type::text AS action_type FROM agent_actions"), conn
        )


@lru_cache(maxsize=1)
def get_failure_labels_df() -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(
            text("SELECT session_id, failure_mode::text AS failure_mode, confidence, evidence_text FROM failure_labels"),
            conn,
        )


def get_experiment_or_404(experiment_id: str) -> dict:
    try:
        eid = uuid.UUID(experiment_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"'{experiment_id}' is not a valid experiment id")

    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT experiment_id::text AS experiment_id, name, control_version, treatment_version, start_date, end_date, traffic_split, status::text AS status "
                "FROM experiments WHERE experiment_id = :eid"
            ),
            {"eid": eid},
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No experiment with id '{experiment_id}'")
    return dict(row)
