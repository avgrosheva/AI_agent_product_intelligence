"""Stage 9 task 4: CLI for the Langfuse connector — the same
preview/import workflow as the API (backend.app.routers.langfuse_connector),
usable without running the API server. Langfuse credentials always come
from LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY in the environment, never
from a command-line argument — an argument ends up in shell history and
in that process's command line, visible to other processes on the same
machine, in a way an environment variable read once at startup is not.

Usage:
  python -m scripts.langfuse_import --project-id <uuid> --domain support \
      --start 2026-01-01T00:00:00 --end 2026-01-31T23:59:59 --mode dry-run
"""

from __future__ import annotations

import argparse
from datetime import datetime

from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.connectors.langfuse.client import LangfuseAPIError, LangfuseClient
from backend.connectors.langfuse.config import LangfuseConfigError, LangfuseConnectionConfig
from backend.connectors.langfuse.schemas import LangfuseExperimentMapping, LangfuseImportMode, LangfuseImportRequest
from backend.connectors.langfuse.service import ExperimentMappingError, preview_import, run_import


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--start", required=True, help="ISO 8601 timestamp")
    parser.add_argument("--end", required=True, help="ISO 8601 timestamp")
    parser.add_argument("--mode", choices=["dry-run", "import"], default="dry-run")
    parser.add_argument("--host", default=None, help="Self-hosted Langfuse host override. Not a secret.")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--experiment-id", default=None)
    parser.add_argument("--experiment-name", default=None)
    parser.add_argument("--control-version", default=None)
    parser.add_argument("--treatment-version", default=None)
    parser.add_argument("--version-field", default="release", choices=["release", "version"])
    parser.add_argument("--outcome-metadata-key", default=None, help="trace.metadata key holding a real business outcome, if the source system attaches one.")
    args = parser.parse_args()

    mapping = LangfuseExperimentMapping(
        external_experiment_id=args.experiment_id,
        name=args.experiment_name,
        control_version=args.control_version,
        treatment_version=args.treatment_version,
        version_field=args.version_field,
        outcome_metadata_key=args.outcome_metadata_key,
    )
    request = LangfuseImportRequest(
        domain=args.domain,
        start=datetime.fromisoformat(args.start),
        end=datetime.fromisoformat(args.end),
        mode=LangfuseImportMode.DRY_RUN if args.mode == "dry-run" else LangfuseImportMode.IMPORT,
        mapping=mapping,
        host=args.host,
        page_size=args.page_size,
    )

    try:
        connection = LangfuseConnectionConfig.from_env(host_override=args.host)
    except LangfuseConfigError as exc:
        raise SystemExit(str(exc))
    client = LangfuseClient(config=connection)

    try:
        if request.mode == LangfuseImportMode.DRY_RUN:
            result = preview_import(client, request)
            print(f"[dry run] {result.traces_fetched} trace(s) fetched, {result.sessions_mapped} mapped, {result.sessions_skipped} skipped")
            for reason in result.skipped_reasons:
                print(f"  skipped: {reason}")
            e = result.derived_experiment
            print(f"Derived experiment {e.external_experiment_id!r}: {e.name!r} (control={e.control_version}, treatment={e.treatment_version})")
        else:
            engine = create_engine(get_database_url())
            result = run_import(engine, client, request, project_id=args.project_id)
            print(
                f"Imported {result.ingestion.sessions_ingested} session(s) into project '{args.project_id}' "
                f"({result.traces_fetched} trace(s) fetched, {result.sessions_skipped} skipped)."
            )
    except LangfuseAPIError as exc:
        raise SystemExit(f"Langfuse API error: status {exc.status_code}")
    except ExperimentMappingError as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
