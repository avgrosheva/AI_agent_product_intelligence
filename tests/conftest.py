"""Shared fixtures for Stage 1 tests.

Running `pytest` end to end: (1) regenerates the dev dataset deterministically,
(2) applies the Alembic baseline migration (idempotent), (3) loads the
generated application tables into Postgres. Requires the project's Postgres
container to be running (see README / docs/ROADMAP.md Stage 1).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from backend.app.db import get_database_url
from datagen.generate import generate_dataset
from datagen.load_to_postgres import load_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DEV_SEED = 42


@pytest.fixture(scope="session")
def dev_seed() -> int:
    return DEV_SEED


@pytest.fixture(scope="session")
def dev_data_dir(dev_seed) -> Path:
    generate_dataset("dev", dev_seed, DATA_DIR)
    return DATA_DIR


@pytest.fixture(scope="session")
def db_engine(dev_data_dir):
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    load_dataset("dev", DATA_DIR, truncate=True)
    engine = create_engine(get_database_url())
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def classified_engine(db_engine):
    """db_engine with failure_labels populated by the deterministic mock
    classifier (RuleBasedMockClient — no API key needed, Stage 2/3 review
    requirement: tests must never depend on live API availability).

    Deliberately a SEPARATE fixture from db_engine, not folded into it:
    db_engine's contract (Stage 1 review) is that failure_labels is empty
    immediately after loading generated data — test_schema_integrity.py's
    test_failure_labels_is_empty_in_stage_1 depends on exactly that. Any
    test that actually needs classified data (failure-mode attribution,
    AI-quality/classifier-provenance API responses, ground-truth-recovery
    validation) must depend on this fixture instead of assuming an earlier,
    unrelated test or an external manual `scripts.run_classification`
    invocation happened to populate it first — that assumption is false
    inside a single pytest session, since db_engine's session-scoped
    truncate-and-reload runs exactly once and nothing else in the suite
    reclassifies afterward.
    """
    from backend.llm.classification_pipeline import classify_all_sessions
    from backend.llm.mock_client import RuleBasedMockClient

    classify_all_sessions(db_engine, RuleBasedMockClient())
    return db_engine


@pytest.fixture(scope="session")
def api_client(classified_engine):
    """FastAPI TestClient against the classified dev database. The app's
    own get_engine() (backend.app.dependencies) connects independently to
    the same Postgres instance via the same DATABASE_URL — this fixture
    only guarantees the data (including classifications) exists first."""
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def experiment_id(classified_engine) -> str:
    with classified_engine.connect() as conn:
        from sqlalchemy import text

        return str(conn.execute(text("SELECT experiment_id FROM experiments LIMIT 1")).scalar_one())
