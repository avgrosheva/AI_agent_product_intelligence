"""Request/response contracts for the Langfuse connector (Stage 9 task
4), shared by both the API router (backend.app.routers.langfuse_connector)
and the CLI (scripts.langfuse_import).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from backend.ingestion.schemas import IngestExperiment, IngestSession, IngestionResponse


class LangfuseImportMode(str, Enum):
    DRY_RUN = "dry_run"
    IMPORT = "import"


class LangfuseExperimentMapping(BaseModel):
    """All fields optional: when the four identity/version fields are
    omitted, the connector derives an experiment from the query itself
    (external_experiment_id/name) and — only when the fetched batch
    contains EXACTLY two distinct agent versions — from that data
    (control_version/treatment_version). It never guesses which two
    versions matter when more or fewer than two are present; see
    backend.connectors.langfuse.service.ExperimentMappingError."""

    external_experiment_id: str | None = None
    name: str | None = None
    control_version: str | None = None
    treatment_version: str | None = None
    version_field: str = Field(default="release", description="Native Langfuse trace field carrying the agent/model version: 'release' or 'version'.")
    outcome_metadata_key: str | None = Field(
        default=None, description="trace.metadata key holding a real business outcome label, when the source system attaches one."
    )


class LangfuseImportRequest(BaseModel):
    domain: str = Field(min_length=1)
    start: datetime
    end: datetime
    mode: LangfuseImportMode = LangfuseImportMode.DRY_RUN
    mapping: LangfuseExperimentMapping = Field(default_factory=LangfuseExperimentMapping)
    host: str | None = Field(
        default=None,
        description="Optional self-hosted Langfuse host override. Never a secret — LANGFUSE_PUBLIC_KEY/"
        "LANGFUSE_SECRET_KEY always come from this server's own environment, never from this request.",
    )
    page_size: int = Field(default=100, ge=1, le=500)


class LangfuseImportPreview(BaseModel):
    domain: str
    mode: str = "dry_run"
    traces_fetched: int
    sessions_mapped: int
    sessions_skipped: int
    skipped_reasons: list[str]
    derived_experiment: IngestExperiment
    sample_sessions: list[IngestSession]


class LangfuseImportResult(BaseModel):
    domain: str
    mode: str = "import"
    traces_fetched: int
    sessions_skipped: int
    skipped_reasons: list[str]
    ingestion: IngestionResponse
