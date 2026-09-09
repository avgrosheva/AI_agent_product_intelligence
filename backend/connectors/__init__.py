"""External-source connectors (Stage 9). Each connector is isolated from
the core: it only ever produces the same backend.ingestion.schemas
shapes any other ingestion source produces, and hands off to the
existing backend.ingestion.service.ingest_batch entry point rather than
writing to the database itself."""
