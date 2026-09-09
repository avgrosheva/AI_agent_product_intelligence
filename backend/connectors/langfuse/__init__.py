"""Langfuse connector (Stage 9 task 1): imports AI-agent traces from
Langfuse's public API into the existing generic ingestion pipeline
(backend.ingestion). See backend.connectors.langfuse.service for the
import workflow, backend.connectors.langfuse.mapper for the
trace-to-IngestSession field mapping, and backend.connectors.langfuse.client
for the HTTP layer."""
