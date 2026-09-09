"""Per-project data-quality monitoring (Stage 11 tasks 5-6): deterministic,
threshold-based checks computed from data already stored by ingestion and
the connectors — never a new source of truth, never a fabricated signal.
See backend.quality.service for the checks, thresholds, and the
connector_runs log both connectors write to."""
