"""Stage 6 task 3: human review of failure attributions. Stores an
analyst's confirm/reject decision (plus an optional corrected mechanism
and a short note) SEPARATELY from the original detector output
(session_failure_attributions) — this package never writes to that table,
only reads it (via DomainAdapter.list_reviewable_attributions) to know
what exists to review. Domain-agnostic: never imports
backend.domains.commerce or backend.domains.support.
"""
