"""Simple file importer (Stage 3 task 5): ingest a JSON or JSONL file
directly into the generic ingestion storage, without needing a running
API server. Calls backend.ingestion.service.ingest_batch directly — the
same function backend/app/routers/ingestion.py's POST endpoint calls, so
a file import and an HTTP POST go through identical validation/persistence.

Two supported file shapes:

  .json  — one JSON object matching the IngestBatchRequest schema exactly:
           {"domain": "...", "experiments": [...], "sessions": [...]}

  .jsonl — one JSON object per line, each tagged with a "type" field:
           {"type": "experiment", ...IngestExperiment fields...}
           {"type": "session", ...IngestSession fields...}
           A --domain argument is required for JSONL (the file itself
           carries no top-level domain field).

Usage:
  python -m scripts.import_sessions data/fixtures/support_sessions.json
  python -m scripts.import_sessions data/fixtures/support_sessions.jsonl --domain support
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.ingestion.schemas import IngestBatchRequest, IngestExperiment, IngestSession
from backend.ingestion.service import IngestionValidationError, ingest_batch


def _load_json(path: Path) -> IngestBatchRequest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return IngestBatchRequest.model_validate(data)


def _load_jsonl(path: Path, domain: str) -> IngestBatchRequest:
    experiments: list[IngestExperiment] = []
    sessions: list[IngestSession] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row_type = row.pop("type", None)
            if row_type == "experiment":
                experiments.append(IngestExperiment.model_validate(row))
            elif row_type == "session":
                sessions.append(IngestSession.model_validate(row))
            else:
                raise ValueError(f"{path}:{line_no}: missing or unknown \"type\" field (expected \"experiment\" or \"session\")")
    return IngestBatchRequest(domain=domain, experiments=experiments, sessions=sessions)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=str, help="path to a .json (IngestBatchRequest) or .jsonl (tagged lines) file")
    parser.add_argument("--domain", type=str, default=None, help="required for .jsonl files")
    args = parser.parse_args()

    path = Path(args.file)
    if path.suffix == ".json":
        request = _load_json(path)
    elif path.suffix == ".jsonl":
        if not args.domain:
            raise SystemExit("--domain is required when importing a .jsonl file")
        request = _load_jsonl(path, args.domain)
    else:
        raise SystemExit(f"unsupported file extension {path.suffix!r} (expected .json or .jsonl)")

    engine = create_engine(get_database_url())
    try:
        response = ingest_batch(engine, request)
    except IngestionValidationError as exc:
        print("INGESTION FAILED — validation errors:")
        for err in exc.errors:
            print(f"  session_index={err.session_index} external_session_id={err.external_session_id!r}: {err.message}")
        raise SystemExit(1)

    print(f"domain={response.domain}")
    print(f"  experiments_ingested: {response.experiments_ingested}")
    print(f"  sessions_ingested:    {response.sessions_ingested}")
    print(f"  messages_ingested:    {response.messages_ingested}")
    print(f"  actions_ingested:     {response.actions_ingested}")
    print(f"  tool_calls_ingested:  {response.tool_calls_ingested}")
    print(f"  metrics_ingested:     {response.metrics_ingested}")


if __name__ == "__main__":
    try:
        main()
    except ValidationError as exc:
        print("INGESTION FAILED — schema validation errors:")
        print(exc)
        raise SystemExit(1)
