# PRD — AI Agent Product Intelligence for Conversational Commerce

## 1. Critical review of the original concept

Before locking scope, here is a direct assessment of the brief as given.

### 1.1 Contradictions

- **"Not a generic LLM observability platform" vs. the requested data model.** The brief asks for `agent_actions`, `tool_calls`, trajectories, tokens, and latency at near-tracing granularity — that *is* the data an observability platform stores. The resolution is not to store less; it's to store only the fields needed to answer product questions (flat tables, no generic span trees, no arbitrary attribute bags) and to make every AI-quality screen justify itself by pointing at a user/business metric. Observability data is a means; the product surface must never present it as an end in itself.
- **"No Langfuse/Braintrust clone" vs. requested trajectory + tool-call storage.** Same tension. Resolved by scoping instrumentation to a fixed, closed set of action types and tool names defined by this project's domain (5-7 action types, 4 tool names) rather than a general-purpose tracing SDK.
- **Two-week solo build vs. the full feature list.** Read literally (synthetic data generator with 5 planted causal effects, 11 tables, a statistics layer with bootstrap + multiple-testing correction, an automated segment-search engine, an LLM failure classifier, 5 polished screens, FastAPI + SQLAlchemy + Alembic + Postgres + Next.js, Docker Compose, tests) this is a 4-6 week project for one engineer, not two. This isn't a contradiction to argue away — it's the single biggest risk to the project. The Roadmap resolves it by explicit sequencing and by naming what gets simplified first if time runs out (see §5 and `ROADMAP.md`).

### 1.2 Weak assumptions

- **"Task success improved but conversion declined" as an off-the-shelf example is good, but it only works if "task success" and "conversion" are structurally different signals.** The brief doesn't say this explicitly, but it must be true by construction: task success has to be an *offline/automated evaluation* of whether the agent's final answer satisfied the stated constraints (computed from the product catalog + constraint parser, independent of what the user actually did), while conversion is an *observed behavioral outcome* (did the user buy). If both were derived from the same signal, the entire motivating example would be circular. This distinction is made explicit in the data model (`evaluations` vs. `sessions`/`product_events`) and called out because it's easy to accidentally collapse the two.
- **"LLM must not calculate metrics or statistics" is right, but the brief doesn't say what the LLM *generates* the labels from.** If the failure-classification LLM is given the same hidden "ground truth scenario" flag the generator planted, classification is trivial and proves nothing. The generator must produce realistic message *text* with enough natural variation that a classifier has to do real work, and the planted ground-truth label must be **physically absent from the application database**, not merely unreferenced by convention (see `DATA_MODEL.md` §8 and `AI_EVALUATION.md` §4 — tightened in the methodology revision below after an initial draft only excluded it by coding convention).
- **"Automated segment discovery" sounds like it implies an open-ended search.** An unbounded search over arbitrary column combinations is a research project, not a two-week feature, and it multiplies the multiple-testing correction problem into something unreviewable. It is scoped down to a fixed, small lattice of pre-registered business dimensions (≤8 single dimensions, pairwise interactions only where both dimensions have a plausible causal story) — see `INVESTIGATION.md`.
- **"Realistic synthetic data" and "planted causal patterns" both need to hold at once.** Pure random data has no findable patterns; pure rule-based data is a lookup table, not a dataset. The generator therefore layers stochastic noise (session-level and user-level random effects, category and platform base rates) on top of *deterministic causal rules* that shift probabilities, so the effects are statistically detectable but not perfectly clean — real analytics work requires separating signal from noise, and a dataset with zero noise would make every downstream statistical technique unnecessary.

### 1.3 Unnecessary complexity to cut for the MVP

- **Alembic migration history.** Alembic is worth keeping (it's expected of a "senior" backend candidate and costs little), but only as a *single* baseline migration generated from the ORM models, not an evolving migration chain. The schema is fixed before implementation starts (this document + `DATA_MODEL.md` are the spec), so there is no need to simulate iterative migrations.
- **A generic LLM-provider plugin system with multiple live providers.** One thin abstraction (a `LLMClient` protocol with an Anthropic implementation and a deterministic rule-based mock used in tests/CI) is enough to prove the point ("not tied to one vendor") without building a provider marketplace.
- **Nested span trees / OpenTelemetry-style tracing.** `agent_actions` and `tool_calls` are flat tables keyed by `session_id` + `sequence_index`, not a generic trace/span graph. This is sufficient to reconstruct a trajectory and is far cheaper to build and query.
- **A generic "rules engine" or "feature flag" system for experiments.** `experiments` is a simple table (two agent versions, a date range, a traffic split); no rollout percentage ramping, no multi-arm bandit, no online stopping rules. The product story is about the *decision* to roll out further, not about building the rollout mechanism itself.
- **A configurable "dimension builder" UI for investigation.** The investigation feature is opinionated and automatic (it runs a fixed algorithm against a fixed set of registered dimensions), not a self-serve pivot-table / BI tool. Letting users define arbitrary custom segments is out of scope.
- **Real-time anything.** All data is batch-generated once per dataset build; there is no streaming ingestion, no live agent running against the app. This is an analytics-and-investigation product over a fixed dataset, not a live monitoring product.

### 1.4 Methodology revision (post-review)

A methodology review of the initial design (this section, §2 onward) caught five correctness issues before implementation started; each is now fixed in the referenced documents rather than merely noted here:

1. **Randomization/analysis unit mismatch.** Agent version is assigned per-user (`DATA_MODEL.md` §3.4), but the original statistics design tested and bootstrapped at the session level, which is pseudoreplication given users have multiple correlated sessions. Fixed by making the user the unit of analysis throughout: per-user cluster statistics feed every significance test, and bootstrap resampling draws users (keeping all their sessions together), not sessions (`STATISTICS.md` §2-4).
2. **A post-treatment segmentation dimension.** "Category of the session's recommended product" can itself be shaped by which agent version is running, so segmenting by it could attribute the agent's own routing behavior to "the segment" rather than to the treatment. Replaced with `requested_category`, read from the user's original request before the agent acts (`DATA_MODEL.md` §3.4, `METRICS.md` §7, `INVESTIGATION.md` §1).
3. **An attribution formula that could exceed 100% and overclaimed causation.** The original "share of incremental abandonment attributable to failure mode X" divided a raw (non-excess) count by an excess total, and used causal wording no correlational classifier label supports. Replaced with an excess-vs-excess decomposition that partitions the observed regression exactly, and relabeled "share of excess abandonment associated with X" (`INVESTIGATION.md` §4).
4. **A planted effect that wasn't actually a treatment effect.** Effect #4 originally degraded both agent versions equally in one category, which a v1-vs-v2 experiment analysis could never attribute to v2. Rewritten as a version-specific regression (`DATA_MODEL.md` §6, effect `monitor_constraint_regression_v2`).
5. **Ground truth excluded by convention rather than structurally.** Fixed by moving all planted-effect ground truth into a separate `validation_ground_truth.parquet` artifact that is never loaded into the application's database at all (`DATA_MODEL.md` §8).

## 2. Product vision

**AI Agent Product Intelligence** is an analytics and investigation tool for teams shipping conversational shopping agents. It answers one question end-to-end: *when a new agent version changes product performance, why, and should we ship it further?*

It is differentiated from generic LLM observability by refusing to stop at "agent behavior changed." Every AI-behavior metric in the product is wired to a downstream user-behavior metric and a downstream economic metric, and the flagship feature (Investigation) exists specifically to walk that causal chain automatically: regression → contributing segment → agent failure mode → trajectory pattern → evidence-backed recommendation.

**The product thesis, stated precisely (revised after Stage 2's real results — see the note at the end of §4):** an aggregate experiment readout can look neutral or mixed — north star flat, no single metric screaming "regression" — while a guardrail has materially regressed and specific user segments are meaningfully worse off. The brief's original motivating example (offline task success clearly up, conversion clearly down) is one dramatic instance of this broader pattern, not the only shape the product needs to handle. This project's own generated dev dataset is itself an example of the broader case, not the dramatic one: aggregate conversion and offline task success come out statistically inconclusive, while abandonment, clarification behavior, response latency, turns, and cost are all significantly worse for v2 — and the underlying planted effects (`DATA_MODEL.md` SS6) show genuinely heterogeneous segment-level results, some favoring v2 and some favoring v1. Investigation's job is to explain *where* the regression actually lives and *why*, regardless of which of these shapes the aggregate happens to take.

## 3. Target users & jobs-to-be-done

| User | Job to be done |
|---|---|
| AI Product Manager | Decide whether to roll out, hold, or roll back an agent version, with a defensible written rationale. |
| Product Analyst | Quantify the size and segment concentration of a metric change; distinguish noise from signal. |
| ML Product Analyst | Connect agent-level behavior (trajectories, tool use, clarification policy) to product KPIs. |
| AI Business Analyst | Translate the above into cost, revenue, and margin impact for a rollout decision. |

All four personas are served by the same screens; they differ only in which screen they open first (PM → Investigation/Overview, Analyst → Experiment/Sessions, ML Analyst → AI Quality/Investigation, Business Analyst → Overview/Experiment economics panel).

## 4. Core user flow (unchanged from brief, restated as the product spec)

1. **Overview** — portfolio view across experiments; a card surfaces "Experiment: Agent v2 vs v1 — aggregate conversion flat, abandonment up" as needing attention. The specific pattern shown here is illustrative of a family of cases the product is built to catch, not a single fixed headline — see the note below.
2. **Experiment** — side-by-side AI, product, and economic metrics for v1 vs v2, each with a confidence interval and a plain-language significance/effect-size verdict. The experiment is flagged "ambiguous — investigate" whenever the north star is flat or improved at the aggregate level while at least one guardrail (abandonment, latency, cost) has regressed significantly, or whenever two metrics move in conflicting directions — not only the specific "task success up, conversion down" shape used as a motivating example earlier in this document.
3. User clicks **Investigate**.
4. The system runs the fixed segment-search algorithm across pre-registered dimensions (constraint-count bucket, platform, requested category, locale, device) and their sanctioned pairwise interactions.
5. Segments are ranked by **excess contribution** to the regression (see `INVESTIGATION.md` §2), with multiple-testing-corrected significance and effect size, not raw p-value.
6. For the top segments, the system pulls `failure_labels` (LLM-classified, taxonomy-constrained) and computes each failure mode's share of *excess* abandonment in that segment vs. the control arm.
7. The system aggregates `agent_actions` sequences per segment into trajectory patterns and flags patterns with disproportionately worse outcomes (e.g., `search→search→search→abandon`).
8. All of the above is assembled into a **Findings** panel: segment, size, metric deltas with CIs, dominant failure mode, dominant harmful trajectory, and a cost/latency note.
9. **Sessions** lets the analyst drop into individual transcripts inside the flagged segment to sanity-check the automated finding against raw evidence (message log, tool calls, products shown).
10. The Investigation page ends in a **structured recommendation**: ship / hold / roll back, the primary reason, the guardrail that's blocking full rollout, and a concrete next action (e.g., "cap clarification when ≥3 constraints already present; re-run offline eval; limited rollout to 10%").

## 5. MVP scope statement

**In scope:** everything in §4, backed by the 11 required tables, a fixed statistical toolkit (proportion tests, continuous tests, bootstrap CIs, effect sizes, Benjamini-Hochberg correction), a bounded automated segment search, an LLM-backed failure classifier validated against planted ground truth, and 5 screens.

**First to simplify if the two weeks run short (in order):** (1) drop the demo-scale dataset and ship only the dev-scale one; (2) reduce AI Quality screen to tables + one chart, no drill-in; (3) reduce pairwise segment interactions to a curated list of 4 instead of a full pairwise grid; (4) replace the LLM classifier's live provider calls with the deterministic mock everywhere (still demonstrates the abstraction and the evaluation methodology) and note this as a "swap the API key in" detail. **Never cut:** the Investigation workflow, the five planted ground-truth effects, or the statistics layer's use of effect size + correction (a p-value-only decision layer would undercut the project's stated thesis).

## 6. Non-goals

As specified in the brief: no real checkout, no production recommendation engine, no model-training infrastructure, no enterprise auth, no microservices/Kafka/Kubernetes, no large agent-framework dependency, no full observability-platform clone, no large admin UI.

## 7. Success criteria for this portfolio project

1. A reviewer can, in under 10 minutes, go from the Overview screen to a written, evidence-backed rollout recommendation that matches the actually-planted ground truth in the demo dataset.
2. The validation harness (`ROADMAP.md` stage 5) shows the automated Investigation recovers all 5 planted effects directionally — correct segment, correct sign, expected mechanism, expected downstream effect (`INVESTIGATION.md` §7) — without requiring exact numeric equality to the generator's internal parameters.
3. Every number shown in the UI is reproducible by re-running a documented SQL query or Python function — nothing is a fixture or a hallucinated LLM output.
4. The codebase is small enough to read end-to-end in an interview setting (target: comfortably under 8k LOC excluding generated migrations/tests).
