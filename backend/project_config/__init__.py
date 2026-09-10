"""Persisted per-project configuration (Stage 12 task 4): lets a project
override a domain's static Python/JSON defaults for metrics, guardrails,
segment dimensions, and economics mappings, plus set a default primary
metric, a monitoring cadence, and which notification event types are
enabled — all through this API, never by editing code or a JSON file.
Persisted config always overrides the domain's static default when
present; commerce/support keep working unchanged when it's absent (Stage
12 task 7). See backend.project_config.service for validation and
backend.project_config.overrides for how a DomainAdapter consults it."""
