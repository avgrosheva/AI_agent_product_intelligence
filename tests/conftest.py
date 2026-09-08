"""Shared fixtures for Stage 1 tests.

Running `pytest` end to end: (1) regenerates the dev dataset deterministically,
(2) applies the Alembic baseline migration (idempotent), (3) loads the
generated application tables into Postgres. Requires the project's Postgres
container to be running (see README / docs/ROADMAP.md Stage 1).

Database isolation (fixed after a real incident: running this suite
truncated and overwrote the demo dataset, because tests and the local demo
app both defaulted to the same `ai_agent_pi` database with nothing to tell
them apart). Before any fixture or backend module resolves a database URL,
this file forces DATABASE_URL to a separate database on the same Postgres
instance (`ai_agent_pi_test` by default, overridable via TEST_DATABASE_URL
for CI) and creates that database if it doesn't exist yet. Every fixture
below still runs exactly the same generate/migrate/load steps, just
against that database — behavior stays deterministic, and nothing here
requires OPENROUTER_API_KEY or any live API access (classified_engine uses
RuleBasedMockClient, never a real LLM client). test_db_isolation.py is a
regression test that fails loudly if this override is ever removed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.app.db import DEFAULT_DATABASE_URL, get_database_url
from datagen.generate import generate_dataset
from datagen.load_to_postgres import load_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DEV_SEED = 42

DEMO_DATABASE_NAME = make_url(DEFAULT_DATABASE_URL).database  # "ai_agent_pi" — must never be the test target
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or make_url(DEFAULT_DATABASE_URL).set(database=f"{DEMO_DATABASE_NAME}_test").render_as_string(hide_password=False)

_test_url = make_url(TEST_DATABASE_URL)
assert _test_url.database != DEMO_DATABASE_NAME, (
    f"TEST_DATABASE_URL must not point at the demo database '{DEMO_DATABASE_NAME}' — "
    "tests must run against an isolated database."
)

# Force every get_database_url() call made from inside this pytest process
# (by fixtures below, by the FastAPI app under TestClient, by alembic in
# the subprocess spawned below, which inherits this env) onto the test
# database, regardless of whatever DATABASE_URL the calling shell set for
# local demo use.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


def _ensure_test_database_exists(test_db_url: str) -> None:
    url = make_url(test_db_url)
    maintenance_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with maintenance_engine.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        maintenance_engine.dispose()


_ensure_test_database_exists(TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def dev_seed() -> int:
    return DEV_SEED


@pytest.fixture(scope="session")
def dev_data_dir(dev_seed) -> Path:
    generate_dataset("dev", dev_seed, DATA_DIR)
    return DATA_DIR


@pytest.fixture(scope="session")
def db_engine(dev_data_dir):
    # Last-line-of-defense re-check, right before the truncating load: if
    # anything between module import and here reset DATABASE_URL to the
    # demo database, refuse to run rather than destroy demo data again.
    resolved = make_url(get_database_url()).database
    assert resolved != DEMO_DATABASE_NAME, (
        f"DATABASE_URL resolved to the demo database '{DEMO_DATABASE_NAME}' inside a test fixture — "
        "refusing to truncate it. This must stay pointed at TEST_DATABASE_URL."
    )
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
