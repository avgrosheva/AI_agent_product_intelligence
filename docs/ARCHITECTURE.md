# Architecture

## 1. System overview

```
┌─────────────────────┐        ┌────────────────────────────────────┐
│  datagen (offline)  │──────▶ │              PostgreSQL              │
│  seeded generator    │  load  │  raw tables (DATA_MODEL.md)          │
└─────────────────────┘        │  + analytics views (METRICS.md)      │
                                └───────────────┬──────────────────────┘
                                                │ SQLAlchemy (read) / asyncpg
                                                ▼
                                ┌────────────────────────────────────┐
                                │           FastAPI backend           │
                                │  routers: experiments, sessions,    │
                                │  investigation, ai-quality, overview │
                                │  ├─ analytics/  (SQL + stats, pure)  │
                                │  ├─ investigation/ (pipeline, §INV)  │
                                │  └─ llm/ (provider abstraction)      │
                                └───────────────┬──────────────────────┘
                                                │ REST/JSON
                                                ▼
                                ┌────────────────────────────────────┐
                                │      Next.js / React frontend       │
                                │  5 screens, Recharts, shared table/  │
                                │  metric-card components              │
                                └────────────────────────────────────┘
```

One backend service, one frontend service, one database, one offline batch generator invoked as a script/CLI (not a running service). No message queue, no cache layer, no separate microservice for the LLM calls (they're a module inside the backend, invoked synchronously at dataset-build/refresh time and cached in `failure_labels`/`evaluations`, not on the request path of any user-facing page — see `AI_EVALUATION.md` §3).

## 2. Why this shape

- **A single backend, not "analytics service" + "API service."** The brief explicitly rules out microservices. Analytics/stats/investigation code is organized as internal Python packages under one FastAPI app, separated by module boundary, not process boundary. This keeps deployment to two containers plus Postgres.
- **Views over materialization, materialized only where the demo dataset needs the speed.** Most `METRICS.md` metrics are plain SQL views computed on read (Postgres handles ~35k sessions with joins trivially at interactive latency). The one materialized object is `session_trajectories` (`INVESTIGATION.md` §5), refreshed once after dataset load, since trajectory string-concatenation is not naturally expressible as a fast ad hoc view.
- **Investigation pipeline runs synchronously on request**, not as a background job with polling. At demo scale (~60 bounded tests, `INVESTIGATION.md` §1) this completes in low single-digit seconds, so a simple "click Investigate → loading state → results" UX is honest and avoids building a job queue.
- **LLM calls are pre-computed, not live-on-click.** Failure classification runs once at dataset build/refresh (`AI_EVALUATION.md` §3); the Investigation page reads cached `failure_labels`. This keeps the demo fast, cheap, and reproducible for interview walkthroughs (no API key required to see the product work, only to regenerate labels).

## 3. Tech stack and rationale

| Layer | Choice | Why |
|---|---|---|
| Backend framework | FastAPI + Pydantic | Typed request/response models double as API docs; matches the brief. |
| ORM/migrations | SQLAlchemy (2.0 style) + Alembic, one baseline migration | Demonstrates real schema-as-code without simulating a migration history that doesn't exist (`PRD.md` §1.3). |
| DB | PostgreSQL | Window functions, `jsonb`, and CTEs are used throughout the analytics layer — Postgres is a functional requirement, not just a default. |
| Analytics | Raw SQL (via SQLAlchemy Core, not the ORM, for analytics queries) + pandas for post-processing/stats | SQL is the graded skill per the brief; pandas/scipy/statsmodels only for what SQL can't express cleanly (bootstrap resampling, BH correction). |
| Stats | scipy.stats, statsmodels | Standard, checkable implementations (`STATISTICS.md` §10). |
| Frontend | Next.js (App Router) + React + TypeScript | Brief's preference; also gives file-based routing that maps cleanly to the 5 screens. |
| Charts | Recharts | Lightweight, sufficient for the required chart types (bar, line, funnel-as-bar, scatter for latency/abandonment). |
| LLM | Anthropic SDK behind `LLMClient` protocol + rule-based mock | See `AI_EVALUATION.md` §3. |
| Infra | Docker Compose (postgres, backend, frontend, one-off `datagen` job) | Brief's constraint; no k8s/Kafka. |
| Testing | pytest (backend: unit tests for stats functions, integration tests for API routes against a test DB, the ground-truth validation suite) + Playwright or Vitest+RTL for a small frontend smoke suite (not exhaustive) | Ground-truth validation is the most important test in the repo; frontend testing is intentionally light per the two-week budget. |

## 4. Data flow for the core scenario (Investigate click)

1. Frontend calls `GET /experiments/{id}/investigation?primary_metric=conversion`.
2. Backend loads session-level rows for both arms (one SQL query, indexed on `experiment_id`), computes the bounded segment scan (`INVESTIGATION.md` §1-3) in-process with pandas/scipy.
3. Backend queries pre-computed `failure_labels` and `session_trajectories` for the top segments (`INVESTIGATION.md` §4-5).
4. Backend assembles `Finding` objects (numbers fully computed), optionally calls `LLMClient.summarize_finding()` per top finding (with the guardrail from `AI_EVALUATION.md` §7), and returns a `InvestigationResult` Pydantic model.
5. Frontend renders the Findings list, each expandable into segment detail (metric deltas + CI, failure-mode bar chart, trajectory pattern table) and links into the Sessions screen filtered to that segment.

## 5. Repository structure

```
AI_agent_product_intelligence/
├── docs/                          # this document set
├── datagen/
│   ├── generate.py                # CLI entry point
│   ├── entities/                  # users.py, products.py, sessions.py, ...
│   ├── effects/                   # one module per planted effect (DATA_MODEL.md §6), all version-specific
│   ├── manifest.py                # writes generation_manifest.json
│   ├── validation_output.py       # writes validation_ground_truth.parquet (DATA_MODEL.md §8) — kept out of load_to_postgres.py entirely
│   └── load_to_postgres.py        # loads only application tables; does not know validation_output.py's output path
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/                # overview.py, experiments.py, sessions.py, investigation.py, ai_quality.py
│   │   ├── models/                 # SQLAlchemy ORM models (mirror DATA_MODEL.md — no ground-truth columns/tables)
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── analytics/
│   │   │   ├── sql/                # .sql files or SQLAlchemy Core query builders, one per METRICS.md metric group (session-level, descriptive)
│   │   │   ├── stats/              # clustering.py, continuous.py, bootstrap.py, correction.py, effect_size.py (STATISTICS.md §10)
│   │   │   └── metrics.py          # thin orchestration
│   │   ├── investigation/
│   │   │   ├── segments.py         # pre-treatment dimension registry + scan (INVESTIGATION.md §1)
│   │   │   ├── scoring.py          # EC score (§2)
│   │   │   ├── failure_attribution.py  # excess-abandonment decomposition, §4
│   │   │   ├── trajectory_attribution.py # §5
│   │   │   └── recommend.py        # §6 decision table
│   │   └── llm/
│   │       ├── client.py           # protocol
│   │       ├── anthropic_client.py
│   │       ├── mock_client.py
│   │       └── prompts/
│   ├── alembic/
│   └── tests/
│       ├── unit/                   # stats functions, scoring
│       └── integration/            # API routes against test DB
├── tests/
│   └── validate_ground_truth.py    # INVESTIGATION.md §7 — reads validation_ground_truth.parquet directly; not part of backend/app, never runs inside the API process
├── frontend/
│   ├── app/
│   │   ├── overview/
│   │   ├── experiments/[id]/
│   │   ├── experiments/[id]/investigation/
│   │   ├── sessions/[id]/
│   │   └── ai-quality/
│   ├── components/                 # MetricCard, ConfidenceBadge, FunnelChart, TrajectoryTable, ...
│   └── lib/api.ts
├── scripts/
│   └── evaluate_classifier.py      # AI_EVALUATION.md §5
├── docker-compose.yml
└── README.md
```

## 6. Cross-cutting conventions

- Every number the frontend renders comes from a typed backend field, never computed client-side beyond formatting (percentages, rounding) — keeps the "deterministic metrics" guarantee end-to-end, not just at the SQL layer.
- All timestamps stored and computed in UTC; display-layer localization is out of scope.
- Config (`LLM_PROVIDER`, DB URL, pricing table version) via environment variables read once at startup, no runtime feature flags.
