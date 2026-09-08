"""Regression test for the test/demo database isolation fix in
conftest.py. This exists because running the backend test suite once
truncated and overwrote the local demo dataset — tests and the demo app
both defaulted to the same `ai_agent_pi` Postgres database, so the
session-scoped db_engine fixture's truncate-and-reload silently replaced
9,000 demo users/~32,300 sessions with the 2,161-session dev profile.

If conftest.py's DATABASE_URL override is ever removed or bypassed, this
test fails loudly instead of the failure mode being "the demo looks
different than it did yesterday."
"""

from __future__ import annotations

from sqlalchemy.engine import make_url

from backend.app.db import get_database_url
from tests.conftest import DEMO_DATABASE_NAME, TEST_DATABASE_URL


def test_test_database_url_is_not_the_demo_database():
    assert make_url(TEST_DATABASE_URL).database != DEMO_DATABASE_NAME


def test_resolved_database_url_is_not_the_demo_database():
    """get_database_url() is what every fixture, the FastAPI app under
    TestClient, and alembic actually connect with — this is the real
    guarantee, not just the constant above."""
    assert make_url(get_database_url()).database != DEMO_DATABASE_NAME


def test_db_engine_fixture_is_connected_to_the_test_database(db_engine):
    assert make_url(str(db_engine.url)).database == make_url(TEST_DATABASE_URL).database
