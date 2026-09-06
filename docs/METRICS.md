# Metric Hierarchy

All formulas below are meant to be implemented as SQL (CTEs over the tables in `DATA_MODEL.md`) or thin pandas wrappers around the same SQL — never as LLM output. Every metric names the tables/columns it is computed from so there is a 1:1 mapping from this document to query code. The formulas below are all **session-level, descriptive** definitions, used for display everywhere in the product (Overview, Experiment, Sessions, AI Quality). When any of them is used to decide whether an experiment result is *significant* — the Experiment screen's badges and everything the Investigation engine ranks — the comparison is instead computed on the per-user cluster statistic described in `STATISTICS.md` §2, because the experiment randomizes users, not sessions. Both numbers (the descriptive session-level one and the inferential cluster-level one) are shown together where a significance verdict is displayed, so the two are never confused for each other.

## 1. North star

**Purchase conversion rate** = `count(sessions where outcome = 'purchase') / count(sessions)`, sliceable by experiment arm, segment, and time. Chosen as north star (not "task success") deliberately: it is the one metric that is both a genuine user outcome and a genuine business outcome, and the entire product thesis is about catching when AI-quality metrics diverge from it. Conversion is the sole north star; it is always reported next to (not blended with) the economic metrics in §6 — cost/session, cost per successful task, revenue/session — rather than folded into a single composite "cost-adjusted conversion" number, which would obscure which of the two (fewer buyers, or more expensive buyers) is actually driving a change and would need a business-defined exchange rate between conversions and dollars that this project has no principled way to set.

## 2. Product metrics (user behavior)

| Metric | Formula | Source |
|---|---|---|
| Conversion rate | see above | `sessions` |
| Add-to-cart rate | `count(outcome in ('purchase','add_to_cart_only')) / count(sessions)` | `sessions` |
| Abandonment rate | `count(outcome = 'abandoned') / count(sessions)` | `sessions` |
| Funnel step-through | impression → click → add_to_cart → purchase, each step's rate over the previous | `product_events`, conditional aggregation per session |
| Time-to-first-recommendation | `min(recommendations.shown_at) - sessions.started_at` | `recommendations`, `sessions` |
| Time-to-goal | for converted sessions: `max(product_events.event_time where event_type='purchase') - sessions.started_at`; for abandoned: time from start to `ended_at` | `product_events`, `sessions` |
| Turns per session | `sessions.num_turns` | `sessions` |
| Click-through rate on recommendations | `count(recommendations.clicked) / count(recommendations)` | `recommendations` |
| Sessions per user | `count(sessions) / count(distinct user_id)` | `sessions` |

## 3. Diagnostic / agent-behavior metrics

These exist purely to explain movements in §2 — every one of them is required to appear on a chart or table next to a product metric, never alone.

| Metric | Formula | Source |
|---|---|---|
| Clarification rate | `count(sessions with ≥1 agent_actions.action_type='clarify') / count(sessions)` | `agent_actions` |
| **Unnecessary-clarification rate** | `count(sessions where num_constraints ≥ 3 AND has clarify action) / count(sessions where num_constraints ≥ 3)` — the diagnostic metric wired directly to planted effect #2 | `sessions`, `agent_actions` |
| Tool calls per session | `count(tool_calls) / count(sessions)` | `tool_calls` |
| Tool success rate | `count(tool_calls.success) / count(tool_calls)` | `tool_calls` |
| Wrong-tool-selection rate | `count(failure_labels.failure_mode='wrong_tool_selection') / count(sessions)` | `failure_labels` |
| Dead-end rate | `count(sessions whose trajectory matches search→search→search→abandon_flow pattern) / count(sessions)` | `agent_actions` trajectory view |
| Action-sequence length | `count(agent_actions) per session` | `agent_actions` |

## 4. AI-quality metrics

| Metric | Formula | Source |
|---|---|---|
| Offline task success rate | `avg(evaluations.score where eval_type='offline_task_success')`, thresholded at ≥0.7 for a binary success rate variant | `evaluations` |
| Constraint satisfaction rate | `avg(recommendations.satisfies_constraints)` for the top-shown recommendation per session | `recommendations` |
| Answer faithfulness score | `avg(evaluations.score where eval_type='answer_faithfulness')` | `evaluations` |
| Failure-mode rate (per mode) | `count(failure_labels.failure_mode = X) / count(sessions)` for each taxonomy value | `failure_labels` |
| Failure-mode share of excess abandonment | an associational decomposition — how much of the *excess* (treatment-attributable) abandonment in a segment co-occurs with failure mode X, net of the baseline rate of X-flagged abandonment already expected under the control arm. See `INVESTIGATION.md` §4 for the exact formula and for why this is deliberately **not** worded as "share attributable to X." | `failure_labels` + `sessions` |

## 5. Guardrails

Guardrails are metrics that must not regress even if the north star improves; the Experiment screen flags a version as "do not roll out" if any guardrail breaches its threshold regardless of north-star direction.

| Guardrail | Threshold logic | Source |
|---|---|---|
| p95 end-to-end session latency | flag if treatment p95 > control p95 × 1.15 | `sessions.total_latency_ms` |
| Tool error rate | flag if treatment > control + 2pp | `tool_calls.success` |
| Unsupported-product-claim rate | flag if treatment > control (any increase is a trust/safety concern) | `failure_labels` |
| Cost per session | flag if treatment > control × 1.20 | `sessions.total_cost_usd` |

## 6. Economic metrics

| Metric | Formula | Source |
|---|---|---|
| LLM cost per session | `total_cost_usd` computed from `(tokens_in × price_in + tokens_out × price_out)` per a versioned pricing table | `sessions`, `messages` |
| Revenue per session | `sum(product_events.price_at_event where event_type='purchase')` per session, 0 if none | `product_events` |
| **Cost per successful task** | `sum(total_cost_usd) / count(sessions where outcome='purchase')` (or offline-task-success as the denominator variant, both reported) | `sessions` |
| Gross margin proxy | `sum(price_at_event × margin_pct) - sum(total_cost_usd)` per segment | `product_events`, `products`, `sessions` |
| Cost-to-serve ratio | `sum(total_cost_usd) / sum(revenue)` | derived |

## 7. Segment dimensions (used consistently across screens and the Investigation engine)

`agent_version` (the treatment axis itself), `constraint_count_bucket` (0-1 / 2 / 3+), `platform`, `device_tier`, `locale`, `requested_category` (the category the user asked for, from `sessions.requested_category` — see `DATA_MODEL.md` §3.4), `persona`. This exact list is the registered dimension set referenced in `INVESTIGATION.md` — metrics and investigation must use the same vocabulary so a segment found by Investigation can be looked up unmodified on the Experiment/Sessions screens.

**Pre-treatment eligibility rule.** Every dimension in this list is fixed at session intake, before the agent takes any action — none of them can be influenced by which agent version the session was assigned to. This is a hard requirement, not a preference: a dimension that the agent version could itself affect (for example, an earlier draft of this list used "category of the session's recommended product," which the agent's own behavior can shift) would make any heterogeneity found along it uninterpretable — a difference could reflect the agent selectively routing certain kinds of sessions into the segment, not a real difference in how v1 and v2 perform for a given kind of request. `requested_category` replaces that earlier post-treatment dimension for exactly this reason.

Post-treatment / agent-generated signals — `agent_actions` trajectories, whether a `clarify` action occurred, tool-call counts and outcomes, `recommendations` properties — are never used to *define* a segment for the heterogeneity scan. They are used only *within* an already-defined (pre-treatment) segment, as explanatory mechanisms for why that segment's outcome differs between arms (`INVESTIGATION.md` §4-5). This distinction — segmentation dimension vs. explanatory mechanism — is enforced by keeping the two in separate registries in code (`investigation/segments.py` vs. `investigation/failure_attribution.py` / `trajectory_attribution.py`, see `ARCHITECTURE.md` §5).

## 8. Metric ownership rule

Every metric in this document is computed by a named SQL view or a named Python function in `backend/analytics/`. The AI-Quality and Investigation screens may display an LLM-generated *narrative sentence* summarizing a set of these metrics, but the numbers themselves are always rendered from the deterministic computation, and the narrative must quote the numbers verbatim rather than re-deriving them — enforced by generating narratives from a template that interpolates already-computed values, not by asking the LLM to compute or restate numbers from raw text.
