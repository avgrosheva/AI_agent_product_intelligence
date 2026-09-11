"""Stage 18 task 3: an append-only record of privileged actions, for
after-the-fact accountability ("who did what, to what, when") -- never a
source of truth for authorization itself (backend.app.auth_deps still
owns that), and never a place secrets or raw request/response payloads
land. See backend.audit.service.record_audit_event's docstring for the
discipline callers must follow when building `event_metadata`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class AuditLogEntry(Base):
    __tablename__ = "audit_log_entries"

    entry_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    # Nullable: some rare privileged events (e.g. a scheduled monitoring
    # run's own release evaluation, which nothing a human triggered right
    # now caused) have no human actor -- recorded with actor_user_id=None
    # rather than a fake system user, so a reader never confuses "we don't
    # know who" with "we know it was nobody."
    actor_user_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    org_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    action: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    target: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    # Named event_metadata, not metadata: SQLAlchemy's DeclarativeBase
    # already owns the attribute name `metadata` (the table registry
    # itself) -- a column literally named `metadata` would shadow it.
    event_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
