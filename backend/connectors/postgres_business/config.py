"""Business Postgres connection configuration (Stage 10 task 2: "connection
settings from environment/secrets"). Read from this server's own
environment only — BUSINESS_DB_HOST/PORT/NAME/USER/PASSWORD/SSLMODE —
never from a request body or CLI argument, exactly like the Langfuse
connector's own credential handling (backend.connectors.langfuse.config).

Only one business-Postgres source is configured per deployment (one set
of env vars), matching the Langfuse connector's own single-external-
source-per-process model — each is scoped to whichever project the
caller names on each enrichment call, not to a persisted per-project
connection record.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class PostgresConfigError(Exception):
    pass


@dataclass(frozen=True)
class PostgresConnectionConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: str | None = None

    @classmethod
    def from_env(cls) -> "PostgresConnectionConfig":
        host = os.environ.get("BUSINESS_DB_HOST")
        dbname = os.environ.get("BUSINESS_DB_NAME")
        user = os.environ.get("BUSINESS_DB_USER")
        password = os.environ.get("BUSINESS_DB_PASSWORD")
        missing = [name for name, value in (("BUSINESS_DB_HOST", host), ("BUSINESS_DB_NAME", dbname), ("BUSINESS_DB_USER", user), ("BUSINESS_DB_PASSWORD", password)) if not value]
        if missing:
            raise PostgresConfigError(
                f"Missing required environment variable(s) for the business Postgres source: {', '.join(missing)}. "
                "The connector never accepts database credentials through a request body or CLI argument."
            )
        return cls(
            host=host,
            port=int(os.environ.get("BUSINESS_DB_PORT", "5432")),
            dbname=dbname,
            user=user,
            password=password,
            sslmode=os.environ.get("BUSINESS_DB_SSLMODE"),
        )

    def to_url(self) -> str:
        url = f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"
        if self.sslmode:
            url += f"?sslmode={self.sslmode}"
        return url

    def __repr__(self) -> str:
        return f"PostgresConnectionConfig(host={self.host!r}, port={self.port}, dbname={self.dbname!r}, user={self.user!r}, password='***redacted***', sslmode={self.sslmode!r})"

    __str__ = __repr__
