"""users, products, experiments (DATA_MODEL.md SS3.1-3.3)."""

import uuid
from datetime import date

from sqlalchemy import ARRAY, Boolean, Date, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base
from backend.app.models.enums import (
    CpuTier,
    ExperimentStatus,
    GpuTier,
    Locale,
    Persona,
    Platform,
    ProductCategory,
)
from backend.app.models.pg_enum import pg_enum


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    signup_date: Mapped[date] = mapped_column(Date, nullable=False)
    platform_pref: Mapped[Platform] = mapped_column(pg_enum(Platform, "platform_enum"), nullable=False)
    locale: Mapped[Locale] = mapped_column(pg_enum(Locale, "locale_enum"), nullable=False)
    persona: Mapped[Persona] = mapped_column(pg_enum(Persona, "persona_enum"), nullable=False)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    category: Mapped[ProductCategory] = mapped_column(
        pg_enum(ProductCategory, "product_category_enum"), nullable=False
    )
    brand: Mapped[str] = mapped_column(String(64), nullable=False)
    price_rub: Mapped[int] = mapped_column(Integer, nullable=False)
    ram_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_tier: Mapped[CpuTier | None] = mapped_column(pg_enum(CpuTier, "cpu_tier_enum"), nullable=True)
    gpu_tier: Mapped[GpuTier | None] = mapped_column(pg_enum(GpuTier, "gpu_tier_enum"), nullable=True)
    screen_in: Mapped[float | None] = mapped_column(Float, nullable=True)
    use_case_tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    margin_pct: Mapped[float] = mapped_column(Float, nullable=False)
    in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Experiment(Base):
    __tablename__ = "experiments"

    experiment_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    control_version: Mapped[str] = mapped_column(String(16), nullable=False)
    treatment_version: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    traffic_split: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[ExperimentStatus] = mapped_column(
        pg_enum(ExperimentStatus, "experiment_status_enum"), nullable=False
    )

    sessions: Mapped[list["Session"]] = relationship(back_populates="experiment")
