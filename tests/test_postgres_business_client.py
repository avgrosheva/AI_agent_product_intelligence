"""Stage 10 tasks 2/6: query-safety validation and connection retry/
failure tests for backend.connectors.postgres_business.client. The
retry tests use the project's own already-running test Postgres as the
"eventually succeeds" target (via an injected engine_factory) rather
than needing a real customer database, plus one test against a real
closed port on localhost to prove genuine connection-refused handling,
not just an injected exception."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from backend.connectors.postgres_business.client import PostgresBusinessClient, PostgresConnectorError, UnsafeQueryError, build_select
from backend.connectors.postgres_business.config import PostgresConnectionConfig
from backend.connectors.postgres_business.schemas import PostgresJoinConfig, PostgresMetricMapping, PostgresSourceConfig


def _source(table: str | None = None, query: str | None = None) -> PostgresSourceConfig:
    return PostgresSourceConfig(
        table=table,
        query=query,
        join=PostgresJoinConfig(join_key_column="external_session_id"),
        metrics=[PostgresMetricMapping(source_column="revenue_usd", metric_name="revenue_usd")],
    )


DUMMY_CONFIG = PostgresConnectionConfig(host="127.0.0.1", port=1, dbname="x", user="x", password="x")


# -- build_select (query/table safety) ----------------------------------


def test_build_select_from_simple_table_name():
    assert build_select(_source(table="orders")) == 'SELECT * FROM "orders"'


def test_build_select_from_schema_qualified_table_name():
    assert build_select(_source(table="public.orders")) == 'SELECT * FROM "public"."orders"'


def test_build_select_rejects_unsafe_table_name():
    with pytest.raises(UnsafeQueryError):
        build_select(_source(table="orders; DROP TABLE users"))


def test_build_select_accepts_plain_select_query():
    assert build_select(_source(query="SELECT * FROM orders WHERE amount > 10")) == "SELECT * FROM orders WHERE amount > 10"


def test_build_select_accepts_query_with_one_trailing_semicolon():
    assert build_select(_source(query="SELECT * FROM orders;")) == "SELECT * FROM orders"


def test_build_select_rejects_multiple_statements():
    with pytest.raises(UnsafeQueryError):
        build_select(_source(query="SELECT * FROM orders; DROP TABLE orders"))


def test_build_select_rejects_non_select_query():
    with pytest.raises(UnsafeQueryError):
        build_select(_source(query="UPDATE orders SET amount = 0"))


def test_build_select_rejects_query_containing_a_write_keyword():
    with pytest.raises(UnsafeQueryError):
        build_select(_source(query="SELECT * FROM orders WHERE 1=1; INSERT INTO orders VALUES (1)"))


def test_build_select_accepts_a_read_only_cte():
    assert build_select(_source(query="WITH recent AS (SELECT * FROM orders) SELECT * FROM recent")).startswith("WITH")


def test_config_repr_redacts_password():
    config = PostgresConnectionConfig(host="db.example.com", port=5432, dbname="orders", user="reporting", password="supersecretpw")
    assert "supersecretpw" not in repr(config)
    assert "reporting" in repr(config)


# -- connect retry/failure -----------------------------------------------


def test_connect_retries_transient_failures_then_succeeds():
    from backend.app.db import get_database_url

    real_url = get_database_url()
    calls = {"n": 0}

    def flaky_factory():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OperationalError("connect", {}, Exception("simulated transient failure"))
        return create_engine(real_url)

    client = PostgresBusinessClient(config=DUMMY_CONFIG, engine_factory=flaky_factory, sleep_fn=lambda s: None, max_retries=5)
    engine = client._connect()
    try:
        assert calls["n"] == 3
    finally:
        engine.dispose()


def test_connect_exhausts_retries_and_raises_connector_error():
    def always_fail():
        raise OperationalError("connect", {}, Exception("down"))

    client = PostgresBusinessClient(config=DUMMY_CONFIG, engine_factory=always_fail, sleep_fn=lambda s: None, max_retries=3)
    with pytest.raises(PostgresConnectorError):
        client._connect()


def test_connection_refused_on_a_real_closed_port_eventually_raises():
    config = PostgresConnectionConfig(host="127.0.0.1", port=59999, dbname="nope", user="nope", password="nope")
    client = PostgresBusinessClient(config=config, max_retries=2, sleep_fn=lambda s: None)
    with pytest.raises(PostgresConnectorError):
        client._connect()
