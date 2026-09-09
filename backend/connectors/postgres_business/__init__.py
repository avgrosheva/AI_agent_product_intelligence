"""Postgres business-data connector (Stage 10): joins a customer's own
Postgres-hosted business data (order/ticket outcomes, revenue, CSAT, ...)
onto already-ingested AI-agent sessions by explicit configured keys, and
persists the result as ordinary metrics through the existing generic
ingestion model (backend.ingestion.service.upsert_metrics) — no separate
analytics path. See backend.connectors.postgres_business.service for the
enrichment workflow, .mapper for the pure join/coercion/dedup logic, and
.client for the read-only, retrying Postgres access layer."""
