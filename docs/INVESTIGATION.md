# Automated Root-Cause Investigation

This is the flagship feature (`PRD.md` §5: never cut). It is triggered by "Investigate" on an ambiguous or regressed experiment and produces the evidence chain: regression → segment → failure mode → trajectory → recommendation.

## 1. Bounded segment lattice of pre-treatment dimensions (not an open-ended search)

Investigation runs over a **pre-registered, fixed set of dimensions**, matching `METRICS.md` §7 exactly so results are directly look-up-able elsewhere in the app:

`agent_version` (fixed as the comparison axis), `constraint_count_bucket` {0-1, 2, 3+}, `platform` {web, ios, android}, `device_tier` {low, mid, high}, `locale` {ru-RU, en-US}, `requested_category` {laptop, monitor, accessory}, `persona`.

**Every one of these is a pre-treatment variable** — fixed at session intake, before the agent takes any action, and therefore not something the agent version itself could have shaped. This is enforced as a rule, not an incidental property: `requested_category` (the category the user asked for, from `sessions.requested_category`) is used here specifically instead of "the category of whatever the agent ended up recommending," because the latter is post-treatment — the agent version can influence what gets recommended, so segmenting by it would risk attributing to "this segment" a difference that is actually caused by differential routing, not by a real difference in how v1 and v2 handle a given kind of request. Post-treatment, agent-generated signals — trajectories, whether a `clarify` action occurred, tool-call counts, recommendation properties — are never used to define a segment here; they are used only downstream as explanatory mechanisms once a segment has already been identified by pre-treatment attributes (§4-5).

- **Single-dimension scan**: every value of every dimension above (≈ 3+3+3+3+2+3+4 = 21 segments).
- **Pairwise scan**: only a curated allowlist of dimension pairs with a plausible causal story, not the full combinatorial grid — `{constraint_count_bucket × platform, constraint_count_bucket × requested_category, platform × device_tier, constraint_count_bucket × persona}`. This keeps the test count bounded (~21 + ~4×9 average cells ≈ 55-60 tests per primary metric, well within the multiple-testing budget in `STATISTICS.md` §6) and keeps every surfaced segment explainable in one sentence.
- Each candidate segment is tested only if it clears the sample-size rule in `STATISTICS.md` §5: **≥30 users per arm**, plus (for rate metrics) ≥10 total events and ≥10 total non-events across both arms. Segments below the fallback floor are skipped and reported as "not enough data," not silently zero-filled or force-tested.
- Segment membership is determined by filtering **sessions** on the pre-treatment attribute (e.g. all sessions where `platform=android`); the statistical test itself then aggregates those filtered sessions up to one row per user before comparing arms, per `STATISTICS.md` §2 — segmentation and clustering are two independent, composable steps in the same pipeline.

## 2. Scoring: excess contribution to the regression

For a chosen primary metric (default: conversion rate; abandonment rate as the secondary lens), computed as the **cluster (per-user) statistic** defined in `STATISTICS.md` §2:

- `overall_delta` = clusterMetric(v2, all users in the experiment) − clusterMetric(v1, all users in the experiment)
- for a segment `s`: `segment_delta(s)` = clusterMetric(v2, users touched by s) − clusterMetric(v1, users touched by s)
- `user_share(s)` = count(distinct users touched by s) / count(distinct users in the experiment) — used in place of a raw session share, since the unit the decomposition should weight by is the unit the inference is computed on
- **excess contribution** `EC(s) = user_share(s) × (segment_delta(s) − overall_delta)`

`EC(s)` answers "how much worse (or better) is this segment than the average segment, weighted by how much of the user base it represents" — a segment that is both large and disproportionately bad drives the score up. This is a lightweight decomposition, not a full Shapley/Oaxaca-Blinder decomposition (that level of rigor is explicitly out of scope per `PRD.md` §1.3), and the methodology note in the UI says so. Session counts and session-level rates are still shown alongside for descriptive "volume" context, but `EC(s)` itself is computed on the cluster statistic so that its ranking is consistent with which segments actually clear the significance bar in §3.

Segments are ranked by `|EC(s)|` **after** the statistical filter in §3 removes non-significant/non-practical segments — a large EC on a non-significant segment is noise, not a finding.

## 3. Pipeline

1. **Screen for ambiguity/regression** on the Experiment page: north star or any guardrail from `METRICS.md` moves in a statistically significant, practically significant direction (or two metrics move in conflicting directions — the literal trigger condition described in the brief), using the cluster-level test from `STATISTICS.md` §3. This produces the "Investigate" affordance; it is not itself part of the Investigation engine, just its entry condition.
2. **Run the bounded scan** (§1) for the primary metric using the matched cluster-level test from `STATISTICS.md` §3, per segment.
3. **Apply Benjamini-Hochberg correction** (`STATISTICS.md` §6) across all p-values from this run.
4. **Filter** to segments passing correction + minimum effect size + the sample-size rule (`STATISTICS.md` §5).
5. **Rank** surviving segments by `|EC(s)|` (§2); take the top 5.
6. For each top segment, **pull failure-mode attribution** (§4) and **trajectory attribution** (§5).
7. **Assemble Findings**: segment definition, user/session counts, metric deltas with cluster-bootstrap CIs, dominant failure mode(s) with their share of excess abandonment, dominant harmful trajectory pattern(s), cost/latency delta, and a template-generated narrative sentence (numbers interpolated, not LLM-computed — `METRICS.md` §8).
8. **Recommendation synthesis** (§6) turns the findings list into a ship/hold/rollback verdict plus a next action.

## 4. Failure-mode attribution: share of excess abandonment

The brief's motivating example is that a failure mode can be common without being what actually drives a regression, and rare without being harmless — that contrast is worth surfacing, but it has to be built from a formula that cannot produce a nonsensical result. An earlier draft of this metric divided *every* abandoned v2 session labeled with failure X by the *total* excess-abandonment count — since the numerator wasn't itself restricted to "excess" sessions, it could exceed the denominator and report shares above 100%, and it was worded as "attributable to X," a causal claim the underlying correlation-based label doesn't support. Both problems are fixed below.

**Step 1 — total excess abandonment in a segment**, unchanged in spirit from the earlier draft, computed on session counts within the segment (this part is a simple rate-times-volume calculation, not a per-mode breakdown yet):

`E(segment) = n_v2(segment) × [abandonment_rate_v2(segment) − abandonment_rate_v1(segment)]`

— i.e., how many more sessions abandoned in v2 than v1's rate would have predicted at v2's volume. `E(segment) > 0` means v2 is worse in this segment; `E(segment) < 0` means v2 is better.

**Step 2 — excess abandonment *co-occurring with* failure mode X**, computed the same way but restricted to sessions labeled X, which is what nets out the baseline:

`E_X(segment) = n_v2(segment) × [abandonment_rate_v2_with_X(segment) − abandonment_rate_v1_with_X(segment)]`

where `abandonment_rate_v?_with_X(segment) = count(sessions in segment, version=v?, outcome=abandoned, session_failure_attributions.mechanism=X, detected=true) / n_v?(segment)`. This subtracts the rate of X-flagged abandonment that would already be expected under v1 at v2's volume, leaving only the *extra* X-flagged abandoned sessions associated with the version change.

**Step 3 — share**: `share_X(segment) = E_X(segment) / E(segment)`, reported only when `|E(segment)|` exceeds a minimum count (e.g. ≥5 excess sessions) so the ratio isn't dominated by noise in a near-zero denominator.

**Hybrid multi-label redesign — this is no longer an exact partition, by design.** A session can independently have zero, one, or several mechanisms detected=true (deterministic detectors and the semantic LLM call each answer their own question independently — see AI_EVALUATION.md), so mechanisms are not mutually exclusive the way the old single `failure_labels.mode` column was. Consequently, summing `E_X(segment)` over every mechanism `X` does **not** reproduce `E(segment)`: it can be less (if some excess-abandoned sessions have no mechanism detected at all — "none" is derived from the absence of any detected=true row, never itself a stored label) or, with overlap, mechanisms' shares individually are still computed the same way and are still not clamped or renormalized to sum to anything in particular. Every other property from the original design is preserved: a share is **not** bounded to [0%, 100%] — a mechanism whose rate *decreased* in v2 contributes a negative share, and another mechanism's share can still exceed 100% — this remains a real, interpretable pattern, not a bug, and the UI shows both the percentage and the raw `E_X` count so it can't be misread as impossible.

**Terminology.** This is reported as **"share of excess abandonment associated with mechanism X,"** never as "share of abandonment attributable to X" or "caused by X." A `session_failure_attributions` row is a detector output (deterministic rule or LLM judgment) correlated with abandonment, not the result of a controlled intervention on that specific mechanism — establishing that fixing X would actually reduce abandonment by this amount would require an experiment that manipulates X directly (e.g., an A/B test on the clarification policy itself), which is out of scope here. The metric's honest claim is: *of the additional abandoned sessions v2 produced in this segment, this fraction were also disproportionately associated with mechanism X, net of the baseline rate* — a decomposition of an observed difference, not a causal estimate of X's effect. The same "associated with / co-occurs with / concentrated among" discipline applies to a mechanism co-occurring with another mechanism in the same session: never "X causes Y" or "X explains N% of Y," since overlap is now expected and unremarkable.

**What is still shown for context**: the raw **share of failures** (`count(mechanism=X, detected=true, version=v2) / count(any mechanism detected=true, version=v2)`) is displayed next to the share of excess abandonment so the common-but-not-decisive vs. rare-but-decisive contrast remains visible — the denominator here is "any mechanism fired," not a single exclusive `!= 'none'` count, since a session can contribute to more than one mechanism's numerator at once.

## 5. Trajectory attribution

**Independence from Stage 2's diagnostic shortcuts.** Stage 2 built a small number of narrowly-scoped, one-off descriptive checks against specific known templates for its own sanity-checking purposes (e.g. `has_consecutive_search` in `session_level_base.sql`, used only by `effects_verification.py`'s `tool_selection_v2_improved` check). Those exist because Stage 2 already knew, from the approved design, which mechanism it was looking for. Stage 3 does not have that luxury and must not borrow it: trajectory patterns here are derived from scratch from `agent_actions` by the grouping procedure below, and their association with outcomes is evaluated on its own terms — no Stage 2 convenience column is read, imported, or otherwise used as a shortcut to a pattern this document already knows is "the" answer.

- `agent_actions` per session are concatenated (ordered by `sequence_index`) into a trajectory string, e.g. `understand_query>search>clarify>search>recommend`. This is a post-treatment, session-level construction — used here as an explanatory mechanism inside a segment that was already identified via pre-treatment attributes (§1), never as a way to define the segment itself.
- Trajectories are grouped by **canonical pattern**: exact strings below a frequency threshold are collapsed to a coarser pattern by counting action-type occurrences and flagging structural features relevant to the taxonomy: `has_clarify`, `num_search_repeats`, `ends_in_abandon`, `num_actions`. This avoids a combinatorial explosion of near-duplicate exact-string patterns while still surfacing meaningful structural culprits like "repeated search with no filter" or "clarify then no follow-up search."
- For the top failing segments from §3, trajectory patterns are cross-tabbed against outcome, and a chi-square test (or Fisher's exact for small cells) flags patterns with a significantly worse outcome distribution than the segment average, again BH-corrected within the run. **This check is performed at the session level, not the cluster level**, and is explicitly labeled "exploratory" in the UI (`STATISTICS.md` §9) — it is a secondary, descriptive mechanism analysis inside a segment whose *primary* significance has already been established by the cluster-aware test in §3, so it is not held to the same clustering-robustness bar as the primary finding.
- Output: e.g. "72% of abandoned sessions in this segment follow `search→clarify→(no further action)`, vs. 24% of non-abandoned sessions in the same segment (p<.01, corrected, exploratory)."

## 6. Recommendation synthesis

A small deterministic decision table (not an LLM judgment) maps the findings shape to a verdict:

| Condition | Verdict |
|---|---|
| North star up, no guardrail breach, no significant negative segment | **Ship fully** |
| North star up or flat, but ≥1 guardrail breached OR a significant negative segment with EC beyond threshold exists | **Hold / targeted fix** — the row this project's own dev dataset actually lands on (`PRD.md` SS2): aggregate conversion flat, abandonment/cost guardrails breached |
| North star down, or guardrail breach with no offsetting improvement | **Roll back** |

The verdict is accompanied by: (a) the primary reason (top finding by `|EC(s)|`), (b) the blocking guardrail(s), and (c) a next action drawn from a small template library keyed to the dominant failure mode (e.g. `unnecessary_clarification` → "cap/gate clarification when ≥3 explicit constraints are already present; re-run offline evaluation; limited rollout"). The LLM may be used only to smooth the wording of the next-action sentence from the template, never to choose the verdict or invent the action.

## 7. Validation against planted ground truth

`tests/validate_ground_truth.py` loads `validation_ground_truth.parquet` (`DATA_MODEL.md` §8), runs the full pipeline above against the demo dataset using only observable columns, and checks recovery **directionally** — correct segment, correct sign, and the expected mechanism/downstream metrics moving as documented — never by exact numeric equality to the generator's internal parameters (which are stochastic shift parameters, not the guaranteed observed effect size). For each planted effect (`DATA_MODEL.md` §6), the assertion checks all four of: known direction, known target segment, expected observable mechanism, and expected downstream effect.

1. **`overclarify_v2`**: appears as a top-5 finding on `constraint_count_bucket=3+`, direction v2 worse; dominant failure mode is `unnecessary_clarification` with a positive share of excess abandonment above 50%; mechanism check — clarification rate in this segment is materially higher for v2 than v1; downstream check — v2's turns, abandonment, and cost are all higher than v1's in this segment.
2. **`android_latency`**: appears as a top-5 finding on `platform=android`, direction v2 worse; mechanism check — v2's mean `search_products` tool latency on this platform exceeds v1's; downstream check — abandonment increases monotonically across latency buckets within this segment (checked via a simple binned correlation, not re-deriving the logistic form exactly).
3. **`monitor_constraint_regression_v2`**: appears as a top-5 finding on `requested_category=monitor`, direction **v2 worse than v1** (revised from the earlier draft, which planted this as affecting both versions equally and therefore could never appear as a v1-vs-v2 finding at all); mechanism check — `wrong_constraint_interpretation` rate for v2 in this segment materially exceeds v1's; downstream check — `recommendations.satisfies_constraints` and conversion are both lower for v2 than v1 in this segment, with no material difference in other categories.
4. **`exploratory_uplift`** and **`tool_selection_v2_improved`** are recoverable as *positive* findings (v2 better, correct sign) — the former on `constraint_count_bucket=0-1`, the latter as a general (non-segment-specific) finding in the overall tool-call-count/cost comparison — confirming the engine correctly signs improvements, not just regressions.
5. No planted effect is missed (false negative), and no more than one spurious top-5 finding appears that doesn't map to a planted effect (bounding false positives, acknowledging the dataset has residual noise by design per `DATA_MODEL.md` §6).

This test suite is the project's primary evidence that "the analytics system finds the planted ground truth," directly answering the brief's requirement #10, and it is written to be robust to the exact numeric values the generator happens to produce for a given seed — it checks the shape of the finding (segment, direction, mechanism, downstream effect), not a specific number.
