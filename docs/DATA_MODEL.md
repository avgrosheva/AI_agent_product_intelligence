# Data Model & Synthetic Dataset Design

> **Scope note:** this document describes the commerce reference domain's synthetic demo/dev dataset and its ground-truth validation design — the tables and generator described below are what `datagen/` produces and what the investigation engine is validated against. The live product's full schema also includes multi-tenant tables (organizations, projects, memberships, refresh tokens, audit log), generic domain-agnostic ingestion tables, and a support reference domain with its own schema — see `ARCHITECTURE.md` for the full picture. The design principles here (session-reconstructable data, pre-treatment vs. post-treatment segmentation, physically isolated ground truth) apply across all domains; the specific tables in §3 are commerce-specific.

## 1. Design principles

- **Session-reconstructable.** Every row in every table traces back to a `session_id`, so a single query set can rebuild: request → agent version → messages → agent trajectory → tool calls → products shown → clicks → cart → purchase/abandonment → latency/tokens/cost → failure labels.
- **Separation of observed behavior from offline evaluation.** `sessions` / `product_events` record what actually happened (behavioral, used for conversion/abandonment). `evaluations` records automated judgments of answer quality ("task success," independent of whether the user bought anything). Collapsing these two would make it structurally impossible to represent task success and conversion moving independently of each other — a dramatic "task success up, conversion down" divergence, or the milder, genuinely mixed pattern this demo dataset actually produces: task success and conversion both roughly flat at the aggregate while several guardrails and specific segments regress.
- **Ground truth is physically separated from the application database, not just excluded by convention.** The generator's causal parameters and per-session planted labels live only in a `validation_ground_truth.parquet` artifact (§8) that is never loaded into the Postgres instance the FastAPI app connects to. There is no `ground_truth_scenario` column and no `source='ground_truth'` row anywhere in the application schema — so a bug in application code cannot accidentally read, join, or expose them, because the data simply is not there. Only `tests/validate_ground_truth.py` and `scripts/evaluate_classifier.py` read the parquet artifact directly, in their own process, entirely outside the app's request path.
- **The unit of randomization is the user, not the session.** `sessions.agent_version` is assigned deterministically by `hash(user_id, experiment_id)`, so every session a given user has within a given experiment carries the same version. This is a design choice (stable per-user experience), and it means sessions within a user are correlated by construction — the statistics layer (`STATISTICS.md` §2) treats the user as the unit of analysis for exactly this reason, not the session.
- **Segment dimensions used for experiment heterogeneity analysis must be pre-treatment.** A variable is eligible to *define* a segment in the Investigation engine's scan only if it is fixed at session intake, before the agent takes any action (e.g. `requested_category`, `constraint_count_bucket`, `platform`, `device_tier`, `locale`, `persona`). Anything the agent or its trajectory could influence (which product category ends up recommended, whether a clarification happened, tool-call counts, recommendation properties) is a *post-treatment* variable and is used only downstream, as an explanatory mechanism inside an already-defined segment — never as the dimension that defines the segment. See `METRICS.md` §7 and `INVESTIGATION.md` §1 for the enforced rule.
- **Flat over nested.** No JSON blobs standing in for relational structure where a table is cheap (e.g., `tool_calls` is a real table, not a JSON column on `agent_actions`). JSON is used only for genuinely variable-shape payloads (`tool_calls.input_json` / `output_json`).

## 2. Entity-relationship overview

```
users ──< sessions >── experiments
             │
             ├──< messages
             ├──< agent_actions ──< tool_calls
             ├──< recommendations >── products
             ├──< product_events >── products (+ users)
             ├──< evaluations
             └──< failure_labels
```

- `sessions.user_id → users.user_id`
- `sessions.experiment_id → experiments.experiment_id`
- `messages.session_id → sessions.session_id`
- `agent_actions.session_id → sessions.session_id`
- `tool_calls.action_id → agent_actions.action_id` (and denormalized `session_id` for cheap filtering)
- `recommendations.session_id → sessions.session_id`, `recommendations.product_id → products.product_id`
- `product_events.session_id → sessions.session_id`, `.product_id → products.product_id`, `.user_id → users.user_id`
- `evaluations.session_id → sessions.session_id`
- `failure_labels.session_id → sessions.session_id`

## 3. Table specifications

### 3.1 `users`
| column | type | notes |
|---|---|---|
| user_id | uuid PK | |
| signup_date | date | uniform over a 12-month window before the experiment |
| platform_pref | enum(web, ios, android) | user's dominant platform, session may still vary |
| locale | enum(ru-RU, en-US) | ru-RU ~85%, matching the RUB-priced domain |
| persona | enum(budget, mainstream, power_user, gift_buyer) | drives constraint style and price sensitivity, not directly exposed as a metric dimension but used to shape query generation |

### 3.2 `products`
| column | type | notes |
|---|---|---|
| product_id | uuid PK | |
| category | enum(laptop, monitor, accessory) | laptop ≈ 60% of catalog, the primary domain; monitor/accessory give the catalog-breadth needed for the category-specific failure effect without expanding domain complexity |
| brand | string | ~12 synthetic brands |
| price_rub | int | category-appropriate lognormal |
| ram_gb | int (laptops) | {8,16,32,64} |
| storage_gb | int (laptops) | {256,512,1024,2048} |
| weight_kg | float (laptops) | 0.9–3.2 |
| cpu_tier | enum(entry, mid, high) | |
| gpu_tier | enum(integrated, entry_discrete, high_discrete) | |
| screen_in | float (laptops) | |
| use_case_tags | text[] | e.g. {programming, gaming, office, content_creation} — drives constraint matching |
| rating | float | 3.0–5.0 |
| margin_pct | float | used for economics (gross margin proxy) |
| in_stock | bool | |

### 3.3 `experiments`
| column | type | notes |
|---|---|---|
| experiment_id | uuid PK | |
| name | string | e.g. "Clarification Policy v2" |
| control_version | string | "v1" |
| treatment_version | string | "v2" |
| start_date / end_date | date | |
| traffic_split | float | fraction to treatment (0.5) |
| status | enum(running, completed) | |

### 3.4 `sessions`
| column | type | notes |
|---|---|---|
| session_id | uuid PK | |
| user_id | FK | |
| experiment_id | FK | |
| agent_version | enum(v1, v2) | assigned by deterministic hash(user_id, experiment_id); **the user is the randomization unit** — every session a user has within this experiment gets the same value (`STATISTICS.md` §2) |
| started_at / ended_at | timestamp | |
| platform | enum(web, ios, android) | may differ session-to-session from `users.platform_pref`; fixed at session intake, pre-treatment |
| device_tier | enum(low, mid, high) | proxy for client-side latency variance; pre-treatment |
| locale | enum | copied/varied from user; pre-treatment |
| initial_query_text | text | generated from a template + persona + constraint set |
| constraints_json | jsonb | structured record of what the user actually specified (category, budget, ram, weight, use_case, brand) — this is what "≥3 strong constraints" is computed from, and is fixed before the agent takes any action |
| requested_category | enum(laptop, monitor, accessory) | **pre-treatment segmentation dimension.** Materialized from `constraints_json->>'category'` — the category the user asked for, not the category of whatever the agent ends up recommending. This replaces an earlier draft of this schema that used the recommended product's category, which is a post-treatment variable (the agent version can influence what gets recommended) and is therefore invalid as an experiment-heterogeneity dimension (see `INVESTIGATION.md` §1). |
| num_constraints | int | derived from `constraints_json`, materialized for query convenience; pre-treatment |
| outcome | enum(purchase, add_to_cart_only, abandoned, no_action) | final session outcome — post-treatment, an outcome variable, never a segmentation dimension |
| num_turns | int | denormalized count of user turns — post-treatment outcome/mechanism variable |
| total_latency_ms | int | sum of action latencies — post-treatment |
| total_tokens_in / total_tokens_out | int | post-treatment |
| total_cost_usd | numeric | derived from token pricing table — post-treatment |

### 3.5 `messages`
| column | type | notes |
|---|---|---|
| message_id | uuid PK | |
| session_id | FK | |
| turn_index | int | |
| sender | enum(user, agent) | |
| text | text | templated with slot variation (synonyms, phrasing, persona tone) so classification is a real task |
| created_at | timestamp | |
| tokens | int | |
| latency_ms | int | agent messages only |

### 3.6 `agent_actions`
| column | type | notes |
|---|---|---|
| action_id | uuid PK | |
| session_id | FK | |
| sequence_index | int | order within session |
| action_type | enum(understand_query, search, filter, clarify, recommend, answer, abandon_flow) | closed set — see §4 for the trajectory grammar |
| started_at | timestamp | |
| latency_ms | int | |
| model_name | string | e.g. "agent-v1-model", "agent-v2-model" (kept abstract, not tied to a real vendor model id) |
| agent_version | enum(v1, v2) | denormalized from session for cheap grouping |

### 3.7 `tool_calls`
| column | type | notes |
|---|---|---|
| tool_call_id | uuid PK | |
| action_id | FK | |
| session_id | FK (denormalized) | |
| tool_name | enum(search_products, filter_products, get_product_details, compare_products) | closed set |
| input_json | jsonb | |
| output_json | jsonb | |
| success | bool | |
| error_type | enum(none, timeout, empty_result, invalid_args) | |
| latency_ms | int | |

### 3.8 `recommendations`
| column | type | notes |
|---|---|---|
| rec_id | uuid PK | |
| session_id | FK | |
| turn_index | int | |
| product_id | FK | |
| rank_position | int | |
| shown_at | timestamp | |
| clicked | bool | |
| clicked_at | timestamp nullable | |
| satisfies_constraints | bool | ground-truth computed by checking `products` attributes against `sessions.constraints_json` — this feeds the offline task-success evaluation deterministically, not via LLM |

### 3.9 `product_events`
| column | type | notes |
|---|---|---|
| event_id | uuid PK | |
| session_id | FK | |
| user_id | FK | |
| product_id | FK | |
| event_type | enum(impression, click, add_to_cart, purchase, remove_from_cart) | |
| event_time | timestamp | |
| price_at_event | int | |

### 3.10 `evaluations`
| column | type | notes |
|---|---|---|
| eval_id | uuid PK | |
| session_id | FK | |
| eval_type | enum(offline_task_success, constraint_satisfaction, answer_faithfulness) | |
| score | float (0-1) | deterministic for constraint_satisfaction/task_success (rule-based against `recommendations.satisfies_constraints`); answer_faithfulness may additionally be informed by the LLM classifier but is still stored as a numeric score, not computed by the LLM at metrics time |
| evaluator | enum(rule_based, llm) | |
| rationale_text | text nullable | LLM-produced justification, display-only |
| created_at | timestamp | |

### 3.11 `failure_labels`
| column | type | notes |
|---|---|---|
| label_id | uuid PK | |
| session_id | FK | |
| failure_mode | enum(unnecessary_clarification, wrong_constraint_interpretation, poor_ranking, wrong_tool_selection, unsupported_product_claim, retrieval_failure, other, none) | closed taxonomy, `none` for sessions with no failure |
| confidence | float | |
| source | enum(llm_classifier) | **single fixed value in the application database.** Ground-truth failure labels are never written here — they exist only in `validation_ground_truth.parquet` (§8). This table therefore always reflects what the classifier actually produced, with no risk of a ground-truth row being accidentally queried by the app; the column is kept (rather than dropped) only so the schema doesn't need to change if a second labeling source is ever added. |
| evidence_text | text | quoted span(s) from `messages` supporting the label |
| created_at | timestamp | |

## 4. Trajectory grammar

`agent_actions.action_type` is drawn from a fixed 7-symbol alphabet, always starting at `understand_query` and ending at one of {`recommend` (with a downstream outcome), `abandon_flow`}. Example trajectories:

- `understand_query → search → filter → recommend`
- `understand_query → search → clarify → search → recommend`
- `understand_query → search → search → search → abandon_flow`

Trajectories are stored as the ordered `agent_actions` rows per session; a materialized view (`session_trajectories`) concatenates `action_type` into a string for pattern grouping (see `INVESTIGATION.md` §4).

## 5. Dataset sizes

| | Dev dataset | Demo dataset |
|---|---|---|
| users | 600 | 9,000 |
| products | 150 (90 laptop / 35 monitor / 25 accessory) | 400 (240/90/70) |
| experiments | 1 (v1 vs v2) | 2 (an earlier throwaway v0-vs-v1, plus the flagship v1-vs-v2) |
| sessions | ~1,800 | ~35,000 |
| messages | ~9,000 | ~180,000 |
| agent_actions | ~7,500 | ~150,000 |
| tool_calls | ~9,500 | ~190,000 |
| recommendations | ~5,000 | ~100,000 |
| product_events | ~11,000 | ~220,000 |
| evaluations | ~5,400 (3 per session) | ~105,000 |
| failure_labels | 1 per session (incl. `none`) | 1 per session (incl. `none`) |

Sizes are chosen so the dev set loads and re-generates in seconds for iteration, and the demo set is large enough that segment-level sample sizes remain usable after slicing three ways. Because the unit of analysis for inference is the **user**, not the session (`STATISTICS.md` §2), the relevant threshold is ≥30 users per arm within the smallest planted segment, not ≥30 sessions. At ~9,000 demo users and ~3.9 sessions/user, even the narrowest planted intersection segment (e.g. `constraint_count_bucket=3+ × platform=android`, roughly 10% of users) leaves on the order of several hundred users per arm — comfortably above threshold. The dev dataset's narrowest single-dimension planted segments (e.g. `constraint_count_bucket=3+`, ~30% of 600 users) clear the threshold too, which is why Roadmap Stage 3 validates a subset of effects against the dev dataset before Stage 5 validates all five against the demo dataset.

## 6. Planted causal effects (ground truth)

All five effects are **version-specific heterogeneous treatment effects**: each one is a difference between v1 and v2 (or, for #1, a difference in how big the same underlying advantage is), so every one of them is in principle discoverable by the v1-vs-v2 experiment analysis the Investigation engine actually runs. None of them is a general product-health issue that would show up identically in both arms — that would not be a "why did v2 differ from v1" finding, and effect #4 was specifically redesigned to fix an earlier draft that made this mistake (it originally affected both versions equally, which no experiment-comparison engine could ever attribute to v2).

Effects are implemented as **probability/parameter shifts** applied on top of baseline stochastic generation (not hard overrides), so patterns are statistically detectable but noisy. Baseline rates and exact deltas are versioned in `generation_manifest.json`. Each effect below is specified with the four fields the validation contract (`INVESTIGATION.md` §7) checks for: **target segment** (always a pre-treatment dimension from `METRICS.md` §7), **direction**, **mechanism** (the observable, post-treatment agent-behavior change that produces the effect — used only for interpretation/attribution, never for defining the segment itself), and **downstream effect** (the product/economic metrics that move as a result).

1. **`exploratory_uplift` — v2 outperforms on exploratory queries.**
   - Target segment: `constraint_count_bucket = 0-1` (pre-treatment).
   - Direction: v2 better than v1.
   - Mechanism: v2's recommendation ranking more often satisfies the (few) stated constraints on the first pass, with no extra clarification needed.
   - Downstream effect: offline task-success +8pp, conversion +3pp vs. v1, turns roughly unchanged.

2. **`overclarify_v2` — v2 over-clarifies on constraint-heavy queries (the flagship regression).**
   - Target segment: `constraint_count_bucket = 3+` (pre-treatment).
   - Direction: v2 worse than v1.
   - Mechanism: for `agent_version = v2` sessions in this segment, the probability of an extra, unnecessary `clarify` action is boosted (~+35pp) even though the user already supplied sufficient constraints; `failure_labels` (ground-truth copy, in the validation artifact only, §8) tags these sessions `unnecessary_clarification`.
   - Downstream effect: `num_turns` +1.3 avg, abandonment +12–15pp, conversion −8–10pp, `total_cost_usd` +18–22%, all measured vs. v1 within the same segment.

3. **`android_latency` — latency-driven abandonment on a specific platform.**
   - Target segment: `platform = android` (pre-treatment).
   - Direction: v2 worse than v1.
   - Mechanism: for v2 sessions on this platform, `tool_calls.latency_ms` for `search_products` is inflated (~+400–700ms); abandonment probability is modeled as a logistic function of total session latency, producing a dose-response relationship rather than a step function.
   - Downstream effect: abandonment rate increases with latency bucket within this segment; conversion drops correspondingly; no material change in offline task-success (the agent's eventual answer is still fine when the user doesn't abandon first).

4. **`monitor_constraint_regression_v2` — version-specific constraint-interpretation regression in one category.**
   - Target segment: `requested_category = monitor` (pre-treatment — the category the user asked for, not what got recommended; see §3.4).
   - Direction: v2 worse than v1 (**revised**: an earlier draft of this effect degraded both versions equally, which is not a treatment effect and would be invisible to a v1-vs-v2 comparison — that version has been discarded).
   - Mechanism: v2's constraint parser conflates "screen size" and "resolution" constraints specifically for monitor requests (a regression introduced in v2, not present in v1's parsing path); baseline `wrong_constraint_interpretation` rate in this segment is ~8% for v1 vs. ~22% for v2.
   - Downstream effect: lower `recommendations.satisfies_constraints` and lower conversion for v2 within this segment only; other categories are unaffected in both versions.

5. **`tool_selection_v2_improved` — v2 has better tool-selection accuracy.**
   - Target segment: all sessions (a main effect, not segment-specific) — included in the overall v1-vs-v2 comparison and in the single-dimension scan as a general (non-interaction) finding.
   - Direction: v2 better than v1.
   - Mechanism: baseline `wrong_tool_selection` rate (redundant `search_products` calls, or calling `get_product_details` before any `filter_products`) is reduced in v2 (~−40% relative).
   - Downstream effect: lower average `tool_calls` per session and lower `total_cost_usd` per session overall for v2 — a genuine improvement that partially offsets effect #2 and is what makes the rollout decision non-obvious rather than a trivial "revert."

Sessions not matching any planted-effect condition behave under baseline rates only. The mapping from `session_id` to which effect (if any) generated it, and the exact parameters used, is recorded only in `validation_ground_truth.parquet` (§8) — there is no `ground_truth_scenario` column in the application's `sessions` table.

## 7. Reproducibility

- Single generator entry point: `python -m datagen.generate --profile dev|demo --seed <int>`.
- Default seeds: `SEED_DEV = 42`, `SEED_DEMO = 2024`. All randomness flows through one `numpy.random.Generator(seed)` instance passed explicitly through the call graph — no module-level global RNG state, no `Faker` calls without a seeded instance.
- Generation order is fixed (users → products → experiments → sessions → messages/actions/tool_calls → recommendations/product_events → evaluations → failure_labels → validation ground truth) so the same seed always produces byte-identical output.
- **Two separate outputs per run**, written to separate locations:
  1. The **application dataset** — every table in §3 except any ground-truth column/row — written as Parquet and bulk-loaded into Postgres for the FastAPI app to read.
  2. The **validation artifact** (`validation_ground_truth.parquet`, §8) — written to a directory the Postgres load script never reads from, and never referenced by any backend/frontend code path.
- `generation_manifest.json` (row counts, seed, planted-effect parameters) is checked into the repo for the dev profile and regenerated on demand for the demo profile.
- CI runs the dev-profile generator and asserts output row counts and a hash of a canonical sample match a committed fixture, guarding against accidental non-determinism (e.g., unseeded UUID generation, dict ordering).

## 8. Validation ground truth artifact and isolation guarantee

`validation_ground_truth.parquet` is the **only** place planted-effect ground truth exists. Schema:

| column | notes |
|---|---|
| session_id | joins to the application DB's `sessions.session_id` for validation purposes only |
| ground_truth_scenario | one of the five `ground_truth_scenario` tags in §6, or `"baseline"` |
| ground_truth_failure_mode | the failure mode (if any) the generator planted for this session, using the same taxonomy as `failure_labels.failure_mode` |
| effect_parameters_ref | pointer into `generation_manifest.json` for the exact parameter values used |

**Isolation guarantee.** This artifact is never loaded into the Postgres database the FastAPI app connects to — not filtered out by a `WHERE` clause or a code convention, but never present as a table, column, or row in that database at all. This makes the leakage this project is designed to avoid (a classifier or a dashboard accidentally reading the answer key) structurally impossible rather than a matter of remembering not to query a column. `tests/validate_ground_truth.py` and `scripts/evaluate_classifier.py` are the only code in the repo permitted to read this file, and they do so with pandas, directly, outside of any application server process — joining it against data pulled from the app's read-only API or DB purely within the test/script process, never inside `backend/app/`. (An alternative considered was isolating ground truth in a separate Postgres schema with no `GRANT` to the app's DB role; the file-based artifact was chosen instead because it removes an entire class of "did we configure the grants correctly" risk.)

## 9. Ground-truth validation contract

`tests/validate_ground_truth.py` loads `validation_ground_truth.parquet`, runs the real Investigation pipeline (`INVESTIGATION.md`) against the application database using only observable columns, and asserts that each of the 5 planted effects is recovered — see `INVESTIGATION.md` §7 for the exact per-effect acceptance criteria (known direction, known segment, expected mechanism, expected downstream effect; recovery is checked directionally, not by exact-equality to the generator's internal parameters). This is the project's core proof of correctness and is treated as a required, not optional, test suite.
