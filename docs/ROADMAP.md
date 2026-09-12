# Roadmap

This document separates what the product does today from credible next steps. It is not a commitment schedule — nothing here is promised to a customer or a deadline.

## Current product

Everything described in the README and `PRD.md` §4 is implemented and in daily use in the demo environment: multi-project/multi-organization tenancy with role-based access and audit logging; data connectors for Langfuse and Postgres business data plus a generic ingestion API; per-project onboarding (data source, metrics, guardrails, segments, economics, monitoring); release evaluation with a deterministic SHIP/HOLD/ROLLBACK verdict and full evidence trail; automated, bounded investigation with multiple-testing correction; a hybrid deterministic + LLM failure-attribution pipeline with a held-out benchmark; human review with confirmation/correction tracking; scheduled monitoring and alerting; data-quality gating; and two reference domains (commerce, support) proving the engine generalizes.

## Near-term product opportunities

These would extend the current product without changing its architecture:

- **More native data-source integrations** beyond Langfuse and Postgres — e.g. a webhook-based generic connector with a guided setup UI, or direct integrations with other common agent-observability tools.
- **Richer review analytics** — trend lines on attribution quality over time, reviewer agreement/inter-rater metrics, and targeted review queues that prioritize the sessions most likely to change a release decision.
- **Segment-builder flexibility within guardrails** — letting a project add its own pre-registered segment dimensions through configuration, still subject to the same pre-treatment eligibility and multiple-testing discipline, rather than a fully open-ended ad hoc query.
- **Customer-specific domain adapters** — a lightweight adapter template and documentation for onboarding a new agent-product shape (e.g. a coding assistant, a support-triage agent) faster than the two reference domains took.
- **Sequential-testing awareness** — surfacing when a monitoring window is still accumulating data versus complete, so an early read isn't mistaken for a final one.

## Production-scale opportunities

These are the kinds of investments a move from a single self-hosted deployment toward serving many customers would require, listed for credibility rather than as commitments:

- **Hosted connector credential management** — per-customer, encrypted-at-rest connector credentials and a control plane, replacing today's deployment-level configuration.
- **Larger-scale job infrastructure** — a background job queue for release evaluation and investigation at data volumes beyond what synchronous computation with per-project caching handles comfortably, with progress reporting instead of a single loading state.
- **Enterprise authentication** — SSO/SAML, SCIM provisioning, and more granular role definitions than the current role set.
- **Multi-region / multi-tenant database isolation** options beyond a single shared Postgres instance with row-level project scoping.
- **Cost and usage controls** for LLM-backed attribution at a scale where per-session cost needs active budget management, not just per-run reporting.
