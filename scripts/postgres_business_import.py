"""Stage 10 task 4: CLI for the Postgres business-data connector — the
same preview/import workflow as the API
(backend.app.routers.postgres_business_connector), usable without running
the API server. Business database credentials always come from
BUSINESS_DB_HOST/PORT/NAME/USER/PASSWORD/SSLMODE in the environment,
never from a command-line argument.

Usage:
  python -m scripts.postgres_business_import --project-id <uuid> --domain support \
      --table support_outcomes --join-key-column external_session_id \
      --metric order_completed:order_completed:boolean \
      --metric revenue_usd:revenue_usd:numeric \
      --mode dry-run
"""

from __future__ import annotations

import argparse

from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.connectors.postgres_business.client import PostgresBusinessClient, PostgresConnectorError, UnsafeQueryError
from backend.connectors.postgres_business.config import PostgresConfigError, PostgresConnectionConfig
from backend.connectors.postgres_business.schemas import (
    PostgresEnrichmentMode,
    PostgresEnrichmentRequest,
    PostgresJoinConfig,
    PostgresMetricMapping,
    PostgresSourceConfig,
)
from backend.connectors.postgres_business.service import JoinConfigError, preview_enrichment, run_enrichment


def _parse_metric(spec: str) -> PostgresMetricMapping:
    parts = spec.split(":")
    if len(parts) not in (2, 3):
        raise SystemExit(f"--metric must be 'source_column:metric_name' or 'source_column:metric_name:value_type', got {spec!r}")
    source_column, metric_name = parts[0], parts[1]
    value_type = parts[2] if len(parts) == 3 else "numeric"
    return PostgresMetricMapping(source_column=source_column, metric_name=metric_name, value_type=value_type)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--table", default=None)
    parser.add_argument("--query", default=None, help="A single read-only SELECT statement, as an alternative to --table.")
    parser.add_argument("--join-key-column", required=True)
    parser.add_argument("--join-key-target", choices=["external_session_id", "external_user_id"], default="external_session_id")
    parser.add_argument("--timestamp-column", default=None)
    parser.add_argument("--metric", action="append", required=True, dest="metrics", help="source_column:metric_name[:numeric|boolean] (repeatable)")
    parser.add_argument("--mode", choices=["dry-run", "import"], default="dry-run")
    args = parser.parse_args()

    source = PostgresSourceConfig(
        table=args.table,
        query=args.query,
        join=PostgresJoinConfig(join_key_column=args.join_key_column, join_key_target=args.join_key_target, timestamp_column=args.timestamp_column),
        metrics=[_parse_metric(spec) for spec in args.metrics],
    )
    request = PostgresEnrichmentRequest(
        domain=args.domain,
        mode=PostgresEnrichmentMode.DRY_RUN if args.mode == "dry-run" else PostgresEnrichmentMode.IMPORT,
        source=source,
    )

    try:
        connection = PostgresConnectionConfig.from_env()
    except PostgresConfigError as exc:
        raise SystemExit(str(exc))
    client = PostgresBusinessClient(config=connection)
    engine = create_engine(get_database_url())

    try:
        if request.mode == PostgresEnrichmentMode.DRY_RUN:
            result = preview_enrichment(engine, client, args.project_id, request)
            print(f"[dry run] {result.source_rows_fetched} row(s) fetched, {result.matched_rows} matched, {len(result.unmatched_source_rows)} unmatched")
            print(f"  {result.null_values_skipped} null value(s) skipped, {len(result.validation_errors)} validation error(s)")
            for issue in result.validation_errors:
                print(f"  validation error: {issue}")
            for row in result.unmatched_source_rows:
                print(f"  unmatched: {row.join_key_value!r} -- {row.reason}")
            if result.sessions_with_no_match:
                print(f"  {len(result.sessions_with_no_match)} ingested session(s) have no matching business row")
        else:
            result = run_enrichment(engine, client, args.project_id, request)
            print(f"Persisted {result.metrics_persisted} metric row(s) from {result.matched_rows} matched source row(s) ({result.source_rows_fetched} fetched).")
    except (UnsafeQueryError, JoinConfigError) as exc:
        raise SystemExit(str(exc))
    except PostgresConnectorError as exc:
        raise SystemExit(f"Business Postgres source error: {exc}")


if __name__ == "__main__":
    main()
