# Statistical Analysis Methodology

> **Scope note:** the statistical engine described here is domain-generic and shared by every domain adapter; commerce-specific examples (session/user fields, specific metrics) are used for concreteness.

## 1. Principle

No product decision in this system is made from a p-value alone. Every comparison reports **effect size + confidence interval + significance test**, computed with respect to the actual unit of randomization, and every automated multi-segment scan applies a **multiple-testing correction** before anything is surfaced as a "finding." The decision layer (`INVESTIGATION.md` §6) combines statistical signal with a minimum practical-significance threshold and guardrail checks.

## 2. Unit of randomization vs. unit of analysis

`sessions.agent_version` is assigned by `hash(user_id, experiment_id)` (`DATA_MODEL.md` §3.4): **the user, not the session, is randomized.** A user keeps the same version across every session they have inside a given experiment. At ~3-4 sessions per user in the demo dataset, this is not a minor footnote — treating sessions as the independent unit when they are not is a textbook pseudoreplication error: sessions from the same user are correlated (a user who is generally quick to abandon, or generally price-sensitive, pulls all of their sessions' outcomes the same direction), so a session-level proportion test or t-test understates the true variance and produces **anti-conservative** p-values and CIs — the system would report findings as significant more often than the data actually supports.

**Resolving principle: match the unit of analysis to the unit of randomization.** Every inferential claim (a significance test, a CI, an effect size that feeds a rollout decision) is computed on **one row per user**, not one row per session. Concretely:

- For a **binary/rate metric** (conversion, abandonment, tool success, task-success-above-threshold), each user's row is their **own rate**: `(# of that user's sessions in this experiment/segment where the event occurred) / (# of that user's sessions in this experiment/segment)`. This produces a continuous value in [0, 1] per user.
- For a **continuous metric** (latency, turns, cost, time-to-goal), each user's row is their **own mean** (or median, matching the skew profile) across their sessions in this experiment/segment.

This has a useful consequence: binary and continuous metrics are handled by **the same downstream machinery** (§3) once reduced to a per-user cluster statistic — there is no separate "proportion test" code path and "continuous test" code path at the top level, only one comparison-of-cluster-statistics path with a choice of test appropriate to the resulting distribution's shape. This is the standard cluster-level-summary approach used for cluster-randomized designs (in the trials literature, sometimes attributed to Donner & Klar), and it is the simplest correct option available: it avoids needing to estimate an intra-cluster correlation coefficient or fit a mixed-effects model, at the cost of weighting every user equally regardless of how many sessions they contributed (§6 documents this trade-off explicitly rather than treating it as free).

**Segment-conditional clustering.** When a segment scan (`INVESTIGATION.md` §1) filters to sessions matching a pre-treatment attribute (e.g. `platform=android`), the same procedure applies to the filtered subset: sessions are filtered first, then grouped by user, then reduced to one row per user *within that filtered subset*, then compared between arms. A user can appear in multiple segments (if their sessions differ on a segment-defining attribute) — that is expected and correct, since segments are properties of sessions/requests, not fixed properties of users.

**Session-level metrics are retained for descriptive reporting** (funnels, "sessions per day," raw counts shown on the Overview/Experiment/Sessions screens) — they are useful and honest as descriptive statistics of what happened. They are simply never the basis for a significance verdict or a rollout decision.

## 3. Test selection and confidence intervals

| Cluster statistic shape | Example metrics | Significance test | Confidence interval | Effect size |
|---|---|---|---|---|
| Roughly symmetric (per-user rate or mean not concentrated near 0/1 or heavily skewed) | conversion rate, task-success rate, latency, turns | Welch's t-test on per-user values (unequal variance, no equal-n assumption — appropriate since arms will rarely have exactly equal user counts) | **Cluster bootstrap** percentile CI (§4) on the difference of per-user means, 10,000 resamples | Cohen's d using the **average-variance** denominator (§7) |
| Skewed / outlier-prone | cost per session (user mean), revenue per session (user mean), time-to-goal | Mann-Whitney U (rank-based, distribution-free) on per-user values | Cluster bootstrap percentile CI on the difference of medians | Rank-biserial correlation |

Only **one** significance test and **one** CI method is used per comparison — an earlier draft of this document ran a t-test and a log-transformed secondary t-test for skewed metrics, and reported both an analytic CI and a bootstrap CI side by side "as a cross-check." That redundancy is removed: it added two extra numbers to every screen without changing any decision, since the two methods agree whenever both are valid and disagreeing cases just raise "which one do I trust" without a documented answer. The cluster bootstrap is used uniformly as the single CI method because it is valid for both the symmetric and skewed cases and is what makes the clustering-aware resampling in §4 actually load-bearing, rather than one of two redundant options.

The naive session-level two-proportion comparison (pooled session counts, Wilson CI) may still be **displayed descriptively** next to the cluster-level result, explicitly labeled "descriptive, session-level, not the basis for significance" — useful for sanity-checking magnitude, never used to decide significance.

## 4. Cluster bootstrap procedure

Implemented once in `stats/bootstrap.py` and reused by every comparison in §3:

1. Reduce sessions to one row per user per arm, per §2 (the per-user rate or mean for the metric being tested, within whatever segment is being tested).
2. For each of 10,000 iterations: resample users **with replacement** within each arm independently (arm sizes held fixed), i.e. draw `n_v1` user-rows with replacement from the v1 user set and `n_v2` user-rows with replacement from the v2 user set.
3. Recompute the statistic of interest (difference in means, difference in medians) on each resampled pair of user sets.
4. The 2.5th/97.5th percentiles of the resulting distribution of differences form the 95% percentile CI.

Resampling **users**, not sessions, and never splitting a user's sessions across resamples, is what preserves the within-user correlation structure — a user is either "in" a given resample (with all of their already-aggregated per-user statistic) or drawn again, but their underlying sessions are never disaggregated and redistributed. This is the direct implementation of "bootstrap must resample users/clusters, preserving all sessions belonging to the sampled user."

## 5. Confidence level, practical significance, and sample-size rules

- Default confidence level: 95% (α = 0.05), configurable per analysis call but not per screen.
- A result is only called a **finding** if it clears three bars simultaneously: (a) statistically significant after correction (§6), (b) effect size at or above a documented minimum-practical-effect threshold (e.g., ≥2pp absolute for conversion/abandonment-style rates, ≥0.2 Cohen's d for continuous metrics — thresholds live in `backend/analytics/thresholds.py`), and (c) enough data for the chosen test to be trustworthy (below).
- **Sample-size rule (revised).** The unit is now users, not sessions, and a flat "≥30" is not sufficient on its own for rate metrics, because a rate estimated from very few observed events is unstable regardless of how many users are in the sample. The rule:
  - **Cluster count**: ≥30 users per arm to use the Welch's t-test / Mann-Whitney path with a CLT-justified interpretation of the bootstrap CI.
  - **Event count (rate metrics only)**: additionally require **≥10 total events and ≥10 total non-events** in the segment across both arms combined (a standard rule-of-thumb threshold for a proportion's sampling distribution to be well-behaved), computed on the underlying session-level counts before per-user aggregation.
  - **Fallback when either threshold isn't met**: if users-per-arm is between ~10 and 30, the test still runs (Mann-Whitney is valid at smaller n than the t-test, and the bootstrap CI remains valid, just wider) but the UI flags the result as "small sample — wide uncertainty" rather than withholding it. Below ~10 users per arm, or below the event-count threshold, no significance verdict is computed at all — the segment is reported descriptively only ("not enough data to test"), which is the explicit "exact/bootstrap fallback where needed" this rule requires: bootstrap remains usable down to the small-cluster-count floor, while below it we stop pretending a test result means anything.

## 6. Multiple-testing correction for automated segment discovery

The Investigation engine runs one hypothesis test per (dimension-or-pair, metric) combination against a bounded, pre-registered set (`INVESTIGATION.md` §1 — ≤ ~40 tests per investigation run, not an unbounded search), each test computed on cluster (user) statistics per §2-4.

- **Benjamini-Hochberg (FDR) procedure** at q = 0.10 is applied across all p-values from a single Investigation run (grouped by primary metric being explained, e.g. all "conversion" tests corrected together, all "abandonment" tests corrected together — not pooled across unrelated metrics, which would over-penalize).
- BH is chosen over Bonferroni deliberately: Bonferroni's family-wise error control is appropriate for a handful of pre-registered confirmatory tests, but the segment scan is exploratory-discovery in nature, where FDR control is the standard, less conservative choice that still bounds false discoveries — this tradeoff is stated explicitly in the Investigation UI's methodology tooltip.
- Segments failing the corrected threshold are not shown as findings; they may still appear in a collapsed "explored, not significant" list for transparency.
- All segment dimensions entering this scan are pre-treatment (`METRICS.md` §7); this is a separate concern from the clustering correction above but is enforced in the same pipeline stage (`investigation/segments.py`).

## 7. Effect-size-first ranking, not p-value ranking

Within the surviving (corrected-significant) segments, ranking for display uses the **excess contribution to the regression** score defined in `INVESTIGATION.md` §2 (computed on user shares and cluster-level deltas, not raw session counts), not the p-value magnitude — a tiny, extremely significant effect in a 0.5%-of-users segment is real but not the story; a large, significant effect in a 25%-of-users segment is the story.

## 8. Effect size: fixing the Welch / Cohen's d mismatch

An earlier draft of this document paired Welch's t-test (which explicitly does not assume equal variances) with the classic Cohen's d formula using a sample-size-weighted pooled standard deviation (which implicitly assumes the two groups share a common variance) — an internally inconsistent combination. The fix: when the significance test is Welch's t-test, the accompanying Cohen's d uses the **unweighted average-variance denominator**, `d = (mean_v2 − mean_v1) / sqrt((s_v1² + s_v2²) / 2)`, rather than the n-weighted pooled-SD form. This denominator does not assume equal variances or equal group sizes and is the standard companion effect size for an unequal-variance test; it is used for every t-test-based comparison in §3. Where the significance test is Mann-Whitney U instead, the effect size is rank-biserial correlation, which has no variance-pooling assumption to get wrong in the first place.

## 9. Known limitations, stated rather than hidden

- **No sequential-testing correction.** The dataset is treated as already collected/complete (a fixed experiment window), so peeking/optional-stopping bias is out of scope; this is stated on the Experiment screen's methodology note rather than silently assumed away, since a real production version of this tool would need it.
- **Segment interactions are not exhaustively tested via a full interaction model (e.g., ANOVA with interaction terms).** The bounded pairwise scan approximates this by directly testing the intersection segment as its own cluster comparison rather than fitting an interaction model. This is a deliberate scope choice, called out in `INVESTIGATION.md`.
- **Equal per-user weighting.** Aggregating to one row per user before testing (§2) means a user with one session and a user with ten sessions count equally in the cluster-level test. This is a deliberate, documented simplification versus a variance-weighted or mixed-effects (e.g. GEE) approach that would weight users by their information content — chosen because it is simpler to implement correctly and to explain, and because the dataset's session-per-user distribution is not extreme enough (§`DATA_MODEL.md` §5) for the unweighted approach to be misleading for this project's purposes.
- **The secondary trajectory-pattern significance check (`INVESTIGATION.md` §5) is session-level, not cluster-level**, and is explicitly labeled "exploratory" in the UI for this reason — it is a descriptive mechanism analysis inside an already-cluster-validated segment finding, not the primary rollout-decision test, so the added complexity of a cluster-robust chi-square was judged not worth it for a secondary/explanatory signal.

## 10. Implementation surface

All statistical functions live in `backend/analytics/stats/` (`clustering.py` — per-user reduction, `continuous.py` — t-test/Mann-Whitney on cluster statistics, `bootstrap.py` — cluster bootstrap, `correction.py` — Benjamini-Hochberg, `effect_size.py`), are pure functions over numpy/pandas inputs (no DB or HTTP calls inside), and are unit-tested against known closed-form results (e.g., an unclustered Welch's t-test checked against `scipy.stats.ttest_ind(equal_var=False)`, and a synthetic-data test that constructs sessions with known injected within-user correlation and asserts the cluster-aware test's false-positive rate under the null stays near the nominal 5% while a naive session-level test's does not) so both the standard-case correctness and the clustering fix itself are verifiably tested, not just asserted in prose.
