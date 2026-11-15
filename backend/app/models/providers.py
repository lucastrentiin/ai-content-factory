from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class ModelProvider(IdMixin, TimestampMixin, Base):
    __tablename__ = "model_providers"
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), index=True)
    adapter: Mapped[str] = mapped_column(String(60))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=50)  # menor = preferido
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(24), default="unknown")
    status_detail: Mapped[str | None] = mapped_column(Text)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    docs_url: Mapped[str | None] = mapped_column(String(300))
    commercial_use_note: Mapped[str] = mapped_column(Text, default="")


class ProviderModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "provider_models"
    __table_args__ = (UniqueConstraint("provider_id", "model_key"),)
    provider_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("model_providers.id", ondelete="CASCADE"), index=True)
    model_key: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(16))
    # unidades: input_per_1m_tokens, output_per_1m_tokens, per_image, per_second, per_1k_chars, per_minute
    pricing: Mapped[dict[str, Any]] = mapped_column(default=dict)
    quality_score: Mapped[float] = mapped_column(Float, default=5)
    speed_score: Mapped[float] = mapped_column(Float, default=5)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    capabilities: Mapped[dict[str, Any]] = mapped_column(default=dict)


class ApiUsage(IdMixin, TimestampMixin, Base):
    __tablename__ = "api_usage"
    provider_key: Mapped[str] = mapped_column(String(60), index=True)
    model_key: Mapped[str | None] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), index=True)
    operation: Mapped[str] = mapped_column(String(60))
    units: Mapped[dict[str, Any]] = mapped_column(default=dict)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    actual_cost_usd: Mapped[float | None] = mapped_column(Float)
    production_job_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("production_jobs.id", ondelete="SET NULL"), index=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="SET NULL"), index=True)
    engine_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("content_engines.id", ondelete="SET NULL"), index=True)
    agent_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("agent_runs.id", ondelete="SET NULL"))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)


class CostLimit(IdMixin, TimestampMixin, Base):
    __tablename__ = "cost_limits"
    scope: Mapped[str] = mapped_column(String(16))  # global|channel|engine|video
    scope_id: Mapped[int | None] = mapped_column(BigInteger)
    period: Mapped[str] = mapped_column(String(16))  # daily|monthly|per_video
    limit_usd: Mapped[float] = mapped_column(Float)
    alert_threshold_pct: Mapped[float] = mapped_column(Float, default=80)
    action: Mapped[str] = mapped_column(String(16), default="block")  # block|alert
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Workflow(IdMixin, TimestampMixin, Base):
    """Automação recorrente/evento (o agendador interno lê esta tabela)."""

    __tablename__ = "workflows"
    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    trigger: Mapped[str] = mapped_column(String(16), default="cron")  # cron|manual|webhook
    schedule: Mapped[str | None] = mapped_column(String(60))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(16))
    last_error: Mapped[str | None] = mapped_column(Text)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
