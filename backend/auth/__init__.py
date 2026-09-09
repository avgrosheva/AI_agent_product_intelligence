"""Stage 7: authentication, organizations, projects, and roles.

Users belong to organizations (many-to-many, via OrganizationMembership,
one role per membership); an organization owns one or more projects, and
a project is the tenancy boundary — it names exactly one domain (e.g.
"commerce" or "support") and is what ingested sessions/experiments,
release evaluations, alerts, and reviews are scoped to (Stage 7 task 2).

Domain-agnostic: this package never imports backend.domains.commerce or
backend.domains.support, the same discipline backend.ingestion/backend.
release/backend.alerts/backend.review already follow.
"""
