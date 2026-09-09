"""FastAPI application (Stage 4). Routers are thin: all business logic,
SQL, statistics, and Investigation logic live in backend.analytics /
backend.investigation / backend.llm, unchanged from Stages 1-3.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.routers import ai_quality, alerts, auth, domains, experiments, ingestion, investigation, langfuse_connector, postgres_business_connector, review, sessions
from backend.app.schemas.common import ErrorResponse
from backend.app.warmup import run_startup_warmup


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Opt-in (AIPI_WARMUP_ON_STARTUP=1) precomputation of the metric table
    and all 3 investigation lenses, so the portfolio demo's first request
    isn't a 24-30s cold computation. See backend.app.warmup for the
    rationale and the cache-lifecycle/invalidation contract. Disabled by
    default so normal dev startup and the test suite are unaffected."""
    run_startup_warmup()
    yield


app = FastAPI(
    title="AI Agent Product Intelligence API",
    description="Analytics, Investigation, and AI-quality API for the conversational-commerce agent experiment (Stage 4).",
    version="0.1.0",
    lifespan=lifespan,
)

# Stage 6 integration fix: the Stage 4 API had no CORS policy because it
# was only ever called from the same-origin test client / curl. The Stage
# 6 frontend is a separately-served Vite dev app (a different origin), so
# without this every request is blocked by the browser before it reaches
# a router. Scoped to localhost dev ports only — this is a local portfolio
# demo, not a deployed multi-origin service.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=ErrorResponse(error_code=str(exc.status_code), detail=exc.detail).model_dump())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(error_code="422", detail=str(exc.errors())).model_dump(),
    )


app.include_router(auth.router)
app.include_router(experiments.router)
app.include_router(investigation.router)
app.include_router(sessions.router)
app.include_router(ai_quality.router)
app.include_router(ingestion.router)
app.include_router(domains.router)
app.include_router(alerts.router)
app.include_router(review.router)
app.include_router(langfuse_connector.router)
app.include_router(postgres_business_connector.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
