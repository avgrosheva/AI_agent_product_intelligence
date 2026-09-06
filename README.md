# AI Agent Product Intelligence

A product-analytics platform that turns a conversational shopping agent's raw behavior into a statistically-grounded, deterministic ship/hold/rollback decision.

## Problem

When a team ships a new version of an AI agent, the aggregate metrics are rarely enough. Conversion can look flat while a specific segment quietly regresses; a guardrail can breach for reasons the headline number never shows. Shipping decisions need a chain that actually connects **agent behavior → product metrics → business impact**, with the statistical discipline to say when a result is real, and the traceability to show *why*. This project builds that chain end-to-end for a v1-vs-v2 conversational commerce agent experiment.

## What the product does

A five-screen internal tool, backed by a FastAPI analytics service:

- **Overview** — is this experiment healthy, in under 10 seconds: north-star metric, primary regression signal, guardrail status, one-sentence summary.
- **Experiment** — the full readout: grouped metric comparison table, shopping funnel, guardrail detail.
- **Investigation** — the flagship screen. Three independent, pre-registered lenses (abandonment, conversion, constraint satisfaction) each run their own bounded segment scan with Benjamini-Hochberg correction, surfacing exactly where a regression concentrates and what behavior is associated with it.
- **Sessions** — drill from any finding into the real sessions behind it, filtered by the same segment.
- **AI Quality** — model/agent behavior quality (task success, constraint satisfaction, failure-mode distribution, classifier evaluation), independent of the business funnel.

## Demo finding

On the current demo dataset, the **Clarification Policy v2** experiment shows:

- **Conversion (north star) is broadly flat** — not statistically significant (p ≈ 0.16).
- **Abandonment is significantly worse in v2** (16.9% → 21.9%, p = 8.5e-23) — the clearest aggregate regression.
- Investigation concentrates that regression in **constraint-heavy requests** (`constraint_count_bucket=3+`: 17.6% → 32.3% abandonment). **Unnecessary clarification is associated with** the excess abandonment in this segment — v2 asks clarifying questions even when the user already gave enough constraints.
- **Android has a separate, non-conversational latency regression** (mean session latency +~50-60% on v2/Android), which independently breaches the p95 latency guardrail. This is latency, not a conversational failure — the UI is careful not to attribute it to the clarification behavior above.
- With a breached guardrail and a statistically significant negative segment, the deterministic decision rule returns **HOLD**, not ship or roll back.

Every claim above is a statistical association or a measured guardrail breach, not a causal proof — the product is built to avoid overstating what a v1-vs-v2 comparison can actually show.

## How Investigation works

- **User-level randomization**: each user sees exactly one version for the life of the experiment; sessions are clustered within users for every inferential test.
- **Cluster-aware inference**: per-user reduction before any significance test, cluster bootstrap for confidence intervals, Welch's t-test or Mann-Whitney U depending on the metric's distribution.
- **Bounded, pre-registered segment discovery**: only pre-treatment dimensions (category, constraint count, platform, device tier, locale, persona) are ever used to define a segment — never a post-treatment/mechanism variable.
- **Benjamini-Hochberg correction**, applied separately within each of the three lenses — findings are never pooled into one ranked list across lenses.
- **Mechanism analysis**: excess-abandonment attribution by failure mode (shares can exceed 100% or go negative — never clamped) and trajectory-pattern association, always reported as "associated with," never "caused by."
- **Deterministic release recommendation**: a fixed, auditable rule table (guardrail breach + negative-segment checks) decides ship/hold/roll-back — never an LLM judgment call.

## Architecture

```
React (Vite/TS) → FastAPI → Analytics / Statistics → Investigation Engine → LLM Classifier → PostgreSQL
```

Validation ground truth (the planted-effect answer key) is **physically separated** from the application: it lives in a standalone parquet file, is never written to the app database, and is read only by the offline evaluation scripts — never by the Investigation engine, the classifier, or any API route.

## Tech stack

- **Frontend**: React 19, TypeScript, Vite, React Router, TanStack Query — no chart library, hand-built visualizations.
- **Backend**: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic.
- **Database**: PostgreSQL 16.
- **Analytics/statistics**: pandas, numpy, scipy, statsmodels — cluster bootstrap, BH correction, Welch/Mann-Whitney.
- **LLM classification**: a protocol-based client abstraction — a deterministic rule-based mock (CI-safe, no API key needed) and a real Anthropic client, swappable without touching the pipeline.
- **Testing**: pytest (backend), Vitest + React Testing Library (frontend unit), Playwright (e2e).

## Data

The demo dataset is **entirely synthetic**, generated by a seeded, deterministic generator — it does not represent real customers, agents, or production traffic. It exists to validate the analytics/investigation pipeline against a known answer key:

- 9,000 users, ~32,300 sessions, 50/50 v1/v2 split.
- **Five planted heterogeneous effects**, each with a known target segment, mechanism, and expected direction — used to verify the Investigation engine actually recovers what was planted, not just what looks interesting.

## Validation

- **All 5 planted effects recovered** at demo scale (one recovered at pairwise-segment granularity rather than the single dimension originally checked — the segment lattice found where the effect concentrates).
- **36/36 data-quality/reconciliation checks pass** (referential integrity, funnel consistency, cost reconciliation, outcome/event agreement).
- **176 backend tests, 25 frontend unit tests, 1 end-to-end test** — all passing (see Final test results below for the current run).
- The mock classifier (`RuleBasedMockClient`) is deterministic and CI-safe; it is never presented as real LLM performance — every screen that surfaces classifier output shows an explicit provenance banner when the active classifier is a mock.
- **Real LLM evaluation**: `AnthropicLLMClient` is code-complete (`backend/llm/anthropic_client.py`) and wired into the same classification pipeline as the mock, but this build was evaluated without an `ANTHROPIC_API_KEY` available in the environment, so the reported classifier numbers above are the mock's. Running `python -m scripts.run_classification --client anthropic` followed by `python -m scripts.evaluate_classifier` with a key present produces the same report against real LLM output — no other code changes needed.

## Run locally

**Backend** (from repo root):
```bash
python -m venv .venv && .venv/Scripts/activate      # or source .venv/bin/activate
pip install -e ".[dev]"

docker run -d --name ai_agent_pi_postgres -p 5434:5432 \
  -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app_password -e POSTGRES_DB=ai_agent_pi \
  postgres:16-alpine

python -m alembic upgrade head
python -m datagen.generate --profile demo --seed 2024   # writes data/demo/*.parquet
python -m datagen.load_to_postgres --profile demo        # loads those parquet files into Postgres
python -m scripts.run_classification --client mock       # populates failure_labels (mock, CI-safe)

AIPI_WARMUP_ON_STARTUP=1 uvicorn backend.app.main:app --port 8123
```

**Frontend** (from `frontend/`):
```bash
npm install
npm run dev        # http://localhost:5173
```

**Tests**:
```bash
pytest                             # backend (excludes @slow demo-scale tests by default)
cd frontend && npm run test        # frontend unit
cd frontend && npx playwright install chromium   # one-time e2e browser install
cd frontend && npm run test:e2e    # e2e (needs backend running against demo data)
```

## Limitations

- All data is synthetic — no real users, agents, or transactions.
- This is a static portfolio demo, not a production service: caching is in-process (no Redis/Celery), and there's no auth, multi-tenancy, or live data ingestion.
- Real LLM classification is code-complete (`AnthropicLLMClient`) but only runs when an API key is supplied; the deterministic mock is the CI-safe default and is always labeled as such in the UI.
