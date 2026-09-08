"""The support domain (Stage 3 proof fixture): a hypothetical
support-ticket-triage agent, entirely unrelated to shopping, used to prove
the generic core/ingestion/adapter layers work for a non-commerce agent
without touching backend/domains/commerce/ or backend/core/. Reads from
the generic ingestion tables (backend.ingestion.models) — never
products/recommendations/product_events."""
