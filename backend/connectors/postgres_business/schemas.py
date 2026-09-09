"""Request/response contracts for the Postgres business-data connector
(Stage 10 task 2/4), shared by the API router
(backend.app.routers.postgres_business_connector) and the CLI
(scripts.postgres_business_import).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PostgresMetricMapping(BaseModel):
    """One column in the source table/query -> one metric name persisted
    on the matched session. `value_type` says how to coerce the raw
    column value: "numeric" (int/float/Decimal or a numeric-looking
    string) or "boolean" (bool, 0/1, or a "true"/"false"-looking string,
    coerced to 1.0/0.0) — a type mismatch is reported, never silently
    coerced to 0."""

    source_column: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    value_type: Literal["numeric", "boolean"] = "numeric"


class PostgresJoinConfig(BaseModel):
    """The ONLY thing that ties a source row to a session — there is no
    fuzzy/inferred join. `join_key_column` must hold values matching this
    project's own `external_session_id` or `external_user_id` (the exact
    strings ingestion itself was given for that session)."""

    join_key_column: str = Field(min_length=1)
    join_key_target: Literal["external_session_id", "external_user_id"] = "external_session_id"
    timestamp_column: str | None = Field(
        default=None,
        description="Column used to pick the most recent row when the source has duplicate rows for the same join key.",
    )


class PostgresSourceConfig(BaseModel):
    """Exactly one of `table` (a plain, safe identifier — quoted and
    SELECT *'d, never string-interpolated) or `query` (a single read-only
    SELECT statement, validated to reject write keywords and multiple
    statements, and additionally executed inside a database-enforced
    read-only transaction regardless). This is a pre-configured, operator
    -supplied data source, not a general SQL execution endpoint — no
    caller-supplied WHERE clause or parameter is ever accepted here."""

    table: str | None = None
    query: str | None = None
    join: PostgresJoinConfig
    metrics: list[PostgresMetricMapping] = Field(min_length=1)

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "PostgresSourceConfig":
        if bool(self.table) == bool(self.query):
            raise ValueError("exactly one of 'table' or 'query' must be set")
        return self


class PostgresEnrichmentMode(str, Enum):
    DRY_RUN = "dry_run"
    IMPORT = "import"


class PostgresEnrichmentRequest(BaseModel):
    domain: str = Field(min_length=1)
    mode: PostgresEnrichmentMode = PostgresEnrichmentMode.DRY_RUN
    source: PostgresSourceConfig


class PostgresValidationIssue(BaseModel):
    join_key_value: str | None
    column: str | None
    message: str


class PostgresUnmatchedRow(BaseModel):
    join_key_value: str | None
    reason: str


class PostgresEnrichmentPreview(BaseModel):
    domain: str
    mode: str = "dry_run"
    source_rows_fetched: int
    matched_rows: int
    unmatched_source_rows: list[PostgresUnmatchedRow]
    sessions_with_no_match: list[str]
    mapped_metrics_preview: list[dict]
    validation_errors: list[PostgresValidationIssue]
    null_values_skipped: int


class PostgresEnrichmentResult(BaseModel):
    domain: str
    mode: str = "import"
    source_rows_fetched: int
    matched_rows: int
    metrics_persisted: int
    unmatched_source_rows: list[PostgresUnmatchedRow]
    sessions_with_no_match: list[str]
    validation_errors: list[PostgresValidationIssue]
    null_values_skipped: int
