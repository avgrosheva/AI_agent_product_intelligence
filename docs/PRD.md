# Product Requirements — AI Agent Product Intelligence

## 1. Product vision

Teams that ship AI agents already have observability: traces, tool calls, latency, token spend. What they don't reliably have is the next step — turning "the agent's behavior changed" into a defensible product decision. **AI Agent Product Intelligence** closes that gap. It answers one question end-to-end, per release: *did this version actually improve the product, where did it regress if not, why, and should we ship, hold, or roll it back?*

The product is differentiated from generic LLM observability by refusing to stop at "agent behavior changed." Every AI-behavior metric is wired to a downstream product or business metric, and the flagship capability (Investigation) exists specifically to walk that chain automatically: regression → contributing segment → agent failure mechanism → representative evidence → a deterministic release recommendation.

**Product thesis.** An aggregate release comparison can look neutral — north-star metric flat, nothing obviously broken — while a guardrail has materially regressed and specific user segments are meaningfully worse off. The product's job is to find where a regression actually concentrates and why, regardless of whether the aggregate signal is dramatic or subtle, and to say so with a confidence level the reader can trust.

## 2. Target users and jobs-to-be-done

| User | Job to be done |
|---|---|
| AI Product Manager | Decide whether to roll out, hold, or roll back an agent version, with a defensible written rationale. |
| Product / ML Analyst | Quantify the size and segment concentration of a metric change; distinguish noise from signal; connect agent-level behavior (trajectories, tool use, clarification policy) to product KPIs. |
| AI Business Analyst | Translate a release's behavior change into cost, revenue, and margin impact. |
| Reviewer / QA | Confirm, reject, or correct what the automated attribution pipeline flagged, and trust that review never silently rewrites the original detection. |
| Platform / Ops owner | Configure data connections, guardrails, and monitoring schedules per project; audit who changed what. |

These personas are served by the same product, differing mainly in which screen they open first — PM and Analyst start at Release Decision or Investigation, the Business Analyst opens the economics panel, the Reviewer lives in Review Queue, and the Platform owner lives in Project Setup and Project Overview.

## 3. Core user flow

1. **Connect data** for a project — via Langfuse, a Postgres business-data connector, or the generic ingestion API — and configure its primary metric, guardrails, and segment dimensions.
2. **Monitor a release** — compare a new agent version against the current one, on the metrics that matter for that project's domain.
3. A guardrail breach, a flat-but-suspicious north star, or a negative segment opens an **investigation**.
4. The system runs a **bounded, pre-registered segment scan** — never an open-ended search — across the project's configured dimensions, with multiple-testing correction applied within the run.
5. Segments are ranked by **excess contribution** to the regression, not raw p-value, so a large effect in a meaningful share of users outranks a tiny, technically-significant effect in a sliver of the population.
6. For the top segments, the system pulls the AI failure-attribution output (deterministic detectors plus one real LLM call per session where interpretation is genuinely required) and computes each mechanism's association with the excess regression.
7. All of the above assembles into **findings**: segment, size, metric deltas with confidence intervals, dominant failure mechanism, and representative sessions a reviewer can open to sanity-check the automated conclusion.
8. The **release decision** is a deterministic verdict — SHIP, HOLD, or ROLLBACK — from a fixed rule table over already-computed numbers, never an LLM judgment call, together with the primary reason and the blocking guardrail if any.
9. **Alerts** fire automatically on a rollback, a blocking guardrail breach, or a hold triggered by a significant negative segment, and can be scheduled to run on a monitoring window rather than only on demand.
10. **Human review** lets a reviewer confirm, reject, or correct any AI-flagged attribution; review outcomes feed a calibration signal (confirmation rate, correction rate) on how much to trust that detector.

## 4. Scope

**In scope today:** everything in §3, backed by a statistical layer with cluster-aware significance testing, confidence intervals, and effect sizes; a bounded automated segment search with multiple-testing correction; a hybrid deterministic + LLM failure-attribution pipeline validated against a held-out benchmark; economics and data-quality gating attached to every release decision; scheduled monitoring and alerting; human review with confirmation/correction tracking; multi-project and multi-organization tenancy with role-based access and audit logging; two reference domains (commerce, support) proving the engine is not hardcoded to one product shape; and a self-service onboarding flow that takes a new project from creation to a first release evaluation.

**Deliberately out of scope for the current product** (see `ROADMAP.md` for what's under consideration next): a hosted multi-customer SaaS control plane with per-customer connector credentials; sequential/online-stopping-aware experiment analysis; a fully open-ended, user-defined segment builder in place of the pre-registered dimension set; enterprise SSO/SCIM; a job queue for release evaluations at a scale beyond what synchronous computation with per-project caching handles comfortably.

## 5. Success criteria

1. A reviewer can go from a project's Overview screen to a written, evidence-backed release recommendation — verdict, reason, guardrail, representative sessions — without leaving the product.
2. Every number the product shows is reproducible by re-running a documented query or function; nothing is a fixture or an unverified LLM output presented as a metric.
3. The failure-attribution pipeline's current architecture meets its own documented acceptance bars on a held-out benchmark (`AI_EVALUATION.md`), and that benchmark — not a deprecated one — is what the product cites as current performance.
4. Adding a new domain (a new kind of agent product) is an adapter, not a rewrite of the statistics, investigation, or release-decision layers.
