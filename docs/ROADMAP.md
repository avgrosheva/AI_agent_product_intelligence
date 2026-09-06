# Screens & Two-Week Roadmap

## 1. The five screens: information hierarchy

### 1.1 Overview
**Purpose**: portfolio-level entry point — "what needs my attention."
- Top: a card per experiment with north-star metric (conversion), delta vs. control, significance badge (from `STATISTICS.md`), and a status chip (`Ship`/`Hold`/`Investigate`/`Roll back` from `INVESTIGATION.md` §6 if already computed, else "Not yet investigated").
- Below: aggregate KPI strip (total sessions, overall conversion, overall LLM cost, overall abandonment) across the selected time range.
- No deep interactivity here — this screen exists to route the user into the Experiment screen for the flagged item.

### 1.2 Experiment
**Purpose**: the head-to-head comparison that surfaces the ambiguity.
- Header: experiment name, versions, date range, sample sizes per arm.
- Metric comparison table/cards grouped exactly by `METRICS.md`'s hierarchy (Product → Diagnostic → AI Quality → Guardrails → Economic), each row showing v1 value, v2 value, absolute + relative delta, CI, and a significance+effect-size badge (not p-value alone, per `STATISTICS.md` §3).
- A funnel chart (impression → click → add_to_cart → purchase) per arm, side by side.
- A prominent **Investigate** button, enabled whenever ≥1 conflicting or guardrail-breaching metric is detected (`INVESTIGATION.md` §3 step 1).

### 1.3 Investigation
**Purpose**: the flagship screen — automated root-cause output.
- Findings list, ranked by `|EC(s)|` (`INVESTIGATION.md` §2), each row: segment definition, user/session counts, metric deltas with cluster-bootstrap CI, dominant failure mode + its share of excess abandonment shown next to its raw share of failures (the common-but-not-decisive vs. rare-but-decisive contrast, `INVESTIGATION.md` §4), dominant trajectory pattern.
- Expand a finding → detail panel: failure-mode bar chart for that segment, trajectory-pattern table with outcome breakdown, a "view sessions" link into the Sessions screen pre-filtered to that segment.
- Bottom: the synthesized **recommendation** block (verdict, primary reason, blocking guardrail, next action) from `INVESTIGATION.md` §6.
- A collapsed "explored, not significant" section for transparency about what was tested and rejected.

### 1.4 Sessions
**Purpose**: ground-truth drill-down / trust-building for the automated findings.
- Filterable/sortable list (by segment dimensions, outcome, failure mode) — filters pre-populate when arriving from an Investigation link.
- Session detail view: message transcript, agent trajectory rendered as a sequence diagram/timeline, tool calls with latency, products shown with click/cart/purchase markers, evaluation scores, and the assigned failure label with its evidence quote.
- This screen is the "show your work" counterpart to Investigation's aggregates — a reviewer should be able to open 3-4 sessions in a flagged segment and visually confirm the automated finding.

### 1.5 AI Quality
**Purpose**: the AI-behavior lens on its own, for the ML Product Analyst persona, always framed against outcomes.
- Failure-mode distribution (overall and by version), each bar clickable to filter Sessions.
- Tool-use quality panel: tool success rate, wrong-tool-selection rate, tool calls per session, by version.
- Trajectory pattern frequency table with associated outcome rates (not just frequency — reinforcing the "not an observability platform" stance by always pairing AI-behavior stats with an outcome column).
- Classifier evaluation report summary (confusion matrix / precision-recall, from `AI_EVALUATION.md` §5) — shown as a small "how much to trust this page" panel, notable because most portfolio projects don't self-report their own AI evaluation's reliability.

## 2. Two-week build sequence

Each stage lists explicit, checkable acceptance criteria. Stages are sequential; a stage is not started until the previous stage's criteria pass.

### Stage 0 — Approval (this deliverable)
**Acceptance criteria**: PRD, ARCHITECTURE, DATA_MODEL, METRICS, STATISTICS, INVESTIGATION, AI_EVALUATION, ROADMAP reviewed and explicitly approved by the user before any code is written.

### Stage 1 — Schema & synthetic data generator (days 1-3)
- Implement SQLAlchemy models for all 11 application tables (no ground-truth columns/tables among them) + Alembic baseline migration.
- Implement `datagen/` per `DATA_MODEL.md`: entities, all 5 version-specific planted effects, manifest writer, `validation_ground_truth.parquet` writer, seeded RNG threading.
- **Acceptance criteria**: `python -m datagen.generate --profile dev --seed 42` produces deterministic output (re-running twice yields identical row hashes); dev dataset row counts match `DATA_MODEL.md` §5 within generation-noise tolerance; `generation_manifest.json` is emitted and contains all 5 effect parameters; loading into Postgres succeeds with all FKs valid (no orphan rows); a schema check confirms the loaded application database contains **no** `ground_truth_scenario` column and no `source='ground_truth'` rows anywhere — `validation_ground_truth.parquet` exists on disk but the Postgres load script never touches it.

### Stage 2 — Analytics SQL & stats layer (days 3-6)
- Implement every metric in `METRICS.md` as a SQL view or query function, computed at the session level for descriptive display.
- Implement `backend/analytics/stats/` per `STATISTICS.md` (per-user cluster reduction, continuous tests on cluster statistics, cluster bootstrap, BH correction, effect sizes), unit-tested against `scipy`/reference values **and** against a synthetic-data check that a naive session-level test's false-positive rate is inflated under a known injected within-user correlation while the cluster-aware test's is not (`STATISTICS.md` §10).
- **Acceptance criteria**: for the dev dataset, a manual query of per-user conversion rate by version matches a hand-computed value; unit tests for every stats function pass against known closed-form/reference-library results, including the clustering false-positive-rate check; a smoke script prints all `METRICS.md` metrics (descriptive, session-level) plus the cluster-level significance verdict for conversion and abandonment for both dev-dataset experiment arms without error.

### Stage 3 — Investigation engine (days 6-9)
- Implement the bounded pre-treatment segment scan, EC scoring, excess-abandonment failure attribution, trajectory attribution, and recommendation synthesis (`INVESTIGATION.md` §1-6), as pure Python over the dev dataset first.
- Implement `failure_labels` LLM classification pipeline (`AI_EVALUATION.md` §3) with both `AnthropicLLMClient` and `RuleBasedMockClient`.
- **Acceptance criteria**: `tests/validate_ground_truth.py` (reading `validation_ground_truth.parquet` directly, never through the app) passes against the **dev** dataset for at least the two highest-priority planted effects (`overclarify_v2`, `tool_selection_v2_improved`), checked directionally (segment, direction, mechanism, downstream effect) per `INVESTIGATION.md` §7 — not by exact parameter match; `scripts/evaluate_classifier.py` produces a confusion matrix meeting the recall/precision bars in `AI_EVALUATION.md` §5 on the dev dataset.

### Stage 4 — FastAPI backend (days 8-10, overlapping Stage 3's tail)
- Wire routers for all 5 screens' data needs; Pydantic schemas for every response.
- **Acceptance criteria**: OpenAPI docs render and every documented endpoint returns valid data against the dev dataset; integration tests hit each router against a test DB.

### Stage 5 — Demo-scale dataset & full ground-truth validation (day 10)
- Run the generator at `--profile demo`, load, run classifier + investigation pipeline end-to-end.
- **Acceptance criteria**: `tests/validate_ground_truth.py` passes for **all 5 planted effects** against the demo dataset, per the directional criteria (known direction, segment, mechanism, downstream effect) in `INVESTIGATION.md` §7 — including `monitor_constraint_regression_v2` recovered specifically as a v2-worse-than-v1 finding, not a general both-versions-affected one.

### Stage 6 — Frontend (days 10-13)
- Build the 5 screens per §1, wired to the FastAPI backend, using Recharts.
- **Acceptance criteria**: the full core user flow (`PRD.md` §4, steps 1-10) is click-through-able end to end against the demo dataset without console errors; a screenshot/GIF walkthrough shows the pattern this project's own data actually produces (`PRD.md` §2) — aggregate conversion and offline task success flat/inconclusive, abandonment/clarification/latency/turns/cost significantly worse for v2, the over-clarification finding surfaced for the constraint-heavy segment, and a hold recommendation — not the brief's dramatic "task success up, conversion down" illustration, which this dataset does not produce and which the generator must not be tuned to force.

### Stage 7 — Polish, tests, docs, Docker Compose (days 13-14)
- `docker-compose up` brings up postgres + backend + frontend + runs the dev-profile generator as an init job, working from a clean clone.
- README with setup instructions, architecture summary, and a "how to verify the ground-truth claims yourself" section pointing at `tests/validate_ground_truth.py`.
- **Acceptance criteria**: a clean-machine clone → `docker-compose up` → working app in under 10 minutes of wall-clock setup (excluding image pulls); `pytest` green; the classifier evaluation report and ground-truth validation results are committed as artifacts in the repo for a reviewer to inspect without re-running anything.

## 3. Explicit fallback order if time runs short

Per `PRD.md` §5: cut demo-scale dataset before AI Quality screen depth; cut AI Quality drill-in before pairwise segment interactions; cut pairwise interactions before switching default `LLM_PROVIDER` to mock; never cut the Investigation workflow, the 5 planted effects, or the effect-size+correction discipline in the stats layer.
