"""Notification channels, delivery, and retry (Stage 12 tasks 1-3).
Notifications are generated only from already-persisted state (a release
evaluation's own status/breached_guardrails/data_quality_status, or a
monitoring run's own failure) — no new decision logic here. See
backend.notifications.service for dispatch/dedup/retry and
backend.notifications.client for the actual HTTP delivery."""
