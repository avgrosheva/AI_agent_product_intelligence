"""Generic attribution-review storage (Stage 6 task 3). One row per
(domain, session_id, failure_mode) an analyst has reviewed — upserted in
place if reviewed again (the latest decision is what's tracked; this is a
current-state table, not an audit log). Never joined to or written by
anything that touches the original detector output.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class AttributionReview(Base):
    __tablename__ = "attribution_reviews"

    review_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    failure_mode: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)  # "confirmed" | "rejected"
    corrected_mechanism: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (UniqueConstraint("domain", "session_id", "failure_mode", name="uq_attribution_reviews_domain_session_mode"),)
