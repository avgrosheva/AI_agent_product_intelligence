"""Read-only, retrying access to the customer's business Postgres
(Stage 10 tasks 2/6). Two layers of "safe read-only query" enforcement:
(1) the configured source is validated before any connection is opened —
a `table` must be a plain identifier (safely quoted, never string-
interpolated) and a `query` must be a single SELECT with no write
keywords; (2) even so, every fetch runs inside a transaction Postgres
itself enforces as read-only (`SET TRANSACTION READ ONLY`), so a
misconfigured or malicious query can't mutate data regardless of what the
configured database role happens to be able to do.

`engine_factory` is the one seam a test overrides (to inject a flaky or
already-known-good SQLAlchemy Engine) instead of depending on a real
customer database being reachable.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from backend.connectors.postgres_business.config import PostgresConnectionConfig
from backend.connectors.postgres_business.schemas import PostgresSourceConfig

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
_FORBIDDEN_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "GRANT", "REVOKE",
    "CREATE", "EXECUTE", "COPY", "CALL", "MERGE", "VACUUM", "REINDEX",
)


class UnsafeQueryError(Exception):
    """Raised for a configured `table`/`query` this connector refuses to
    run — never for a per-row data problem (see PostgresConnectorError /
    mapper.TypeMismatchError for those)."""


class PostgresConnectorError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


def build_select(source: PostgresSourceConfig) -> str:
    """Turns a validated PostgresSourceConfig into the exact SQL text to
    run. Never accepts a caller-supplied WHERE clause, parameter, or
    anything else beyond the pre-configured table/query — this is not a
    general SQL execution endpoint (Stage 10 task 2)."""
    if source.table is not None:
        if not _SAFE_IDENTIFIER.match(source.table):
            raise UnsafeQueryError(f"invalid table name {source.table!r} — expected [schema.]table using only letters, digits, and underscores")
        quoted = ".".join(f'"{part}"' for part in source.table.split("."))
        return f"SELECT * FROM {quoted}"

    query = (source.query or "").strip()
    body = query[:-1].strip() if query.endswith(";") else query
    if ";" in body:
        raise UnsafeQueryError("query must be a single statement (no ';' other than one optional trailing one)")
    if not (body[:6].upper() == "SELECT" or body[:4].upper() == "WITH"):
        raise UnsafeQueryError("query must start with SELECT (or a read-only WITH ... SELECT CTE)")
    upper = body.upper()
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            raise UnsafeQueryError(f"query contains a disallowed keyword: {keyword}")
    return body


@dataclass
class PostgresBusinessClient:
    config: PostgresConnectionConfig
    max_retries: int = 3
    sleep_fn: Callable[[float], None] = time.sleep
    engine_factory: Callable[[], Engine] | None = None

    def _default_engine_factory(self) -> Engine:
        return create_engine(self.config.to_url(), connect_args={"connect_timeout": 5})

    def _connect(self) -> Engine:
        factory = self.engine_factory or self._default_engine_factory
        last_error: OperationalError | None = None
        for attempt in range(self.max_retries):
            try:
                engine = factory()
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return engine
            except OperationalError as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    self.sleep_fn(0.5 * (attempt + 1))
                    continue
        raise PostgresConnectorError(f"could not connect to the business Postgres source after {self.max_retries} attempt(s): {last_error}")

    def fetch_rows(self, source: PostgresSourceConfig) -> list[dict]:
        sql_text = build_select(source)  # validated before any connection is opened
        engine = self._connect()
        try:
            with engine.connect() as conn:
                conn.execute(text("SET TRANSACTION READ ONLY"))
                result = conn.execute(text(sql_text))
                columns = list(result.keys())
                return [dict(zip(columns, row)) for row in result.fetchall()]
        except OperationalError as exc:
            raise PostgresConnectorError(f"business Postgres source query failed: {exc}") from exc
        finally:
            engine.dispose()
