"""sessions, messages, agent_actions, tool_calls (DATA_MODEL.md SS3.4-3.7).

Note: there is deliberately no `ground_truth_scenario` column on Session —
planted-effect ground truth lives only in validation_ground_truth.parquet
(DATA_MODEL.md SS8), never in this table.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base
from backend.app.models.enums import (
    ActionType,
    AgentVersion,
    DeviceTier,
    Locale,
    MessageSender,
    Platform,
    ProductCategory,
    SessionOutcome,
    ToolErrorType,
    ToolName,
)
from backend.app.models.pg_enum import pg_enum


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("experiments.experiment_id"), nullable=False, index=True
    )
    agent_version: Mapped[AgentVersion] = mapped_column(
        pg_enum(AgentVersion, "agent_version_enum"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    platform: Mapped[Platform] = mapped_column(pg_enum(Platform, "platform_enum"), nullable=False)
    device_tier: Mapped[DeviceTier] = mapped_column(
        pg_enum(DeviceTier, "device_tier_enum"), nullable=False
    )
    locale: Mapped[Locale] = mapped_column(pg_enum(Locale, "locale_enum"), nullable=False)
    initial_query_text: Mapped[str] = mapped_column(Text, nullable=False)
    constraints_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    requested_category: Mapped[ProductCategory] = mapped_column(
        pg_enum(ProductCategory, "product_category_enum"),
        nullable=False,
        index=True,
    )
    num_constraints: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    outcome: Mapped[SessionOutcome] = mapped_column(
        pg_enum(SessionOutcome, "session_outcome_enum"), nullable=False
    )
    num_turns: Mapped[int] = mapped_column(Integer, nullable=False)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens_in: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens_out: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)

    user: Mapped["User"] = relationship(back_populates="sessions")  # noqa: F821
    experiment: Mapped["Experiment"] = relationship(back_populates="sessions")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(back_populates="session")
    agent_actions: Mapped[list["AgentAction"]] = relationship(back_populates="session")


class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sender: Mapped[MessageSender] = mapped_column(
        pg_enum(MessageSender, "message_sender_enum"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="messages")


class AgentAction(Base):
    __tablename__ = "agent_actions"

    action_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[ActionType] = mapped_column(
        pg_enum(ActionType, "action_type_enum"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_version: Mapped[AgentVersion] = mapped_column(
        pg_enum(AgentVersion, "agent_version_enum"), nullable=False
    )

    session: Mapped["Session"] = relationship(back_populates="agent_actions")
    tool_calls: Mapped[list["ToolCall"]] = relationship(back_populates="action")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    tool_call_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    action_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_actions.action_id"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    tool_name: Mapped[ToolName] = mapped_column(pg_enum(ToolName, "tool_name_enum"), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_type: Mapped[ToolErrorType] = mapped_column(
        pg_enum(ToolErrorType, "tool_error_type_enum"), nullable=False
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    action: Mapped["AgentAction"] = relationship(back_populates="tool_calls")
