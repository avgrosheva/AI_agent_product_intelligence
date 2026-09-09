"""Stage 5: release monitoring — evaluating one experiment's v1-vs-v2
comparison through the generic Investigation engine, persisting the
result, and exposing the latest status. Domain-agnostic: takes a domain
name, an experiment id, and an InvestigationConfig/dataframes already
built by the caller (backend.app.domain_registry) — this package never
imports backend.domains.commerce or backend.domains.support itself, the
same discipline backend.ingestion already follows."""
