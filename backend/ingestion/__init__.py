"""Generic ingestion layer (Stage 3): a normalized contract, storage, and
service for an external agent team to send its own session logs into the
platform without depending on the commerce demo schema. See:

- backend.ingestion.schemas    — the JSON-friendly ingestion contract
- backend.ingestion.models     — generic storage (never products/
  recommendations/product_events)
- backend.ingestion.service    — validation + idempotent persistence
"""
