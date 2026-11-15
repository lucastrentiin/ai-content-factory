from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Publication(IdMixin, TimestampMixin, Base):
    __tablename__ = "publications"
    production_job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    social_account_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("social_accounts.id", ondelete="SET NULL"))
    platform_key: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list[Any]] = mapped_column(default=list)
    cover_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    video_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    mode: Mapped[str] = mapped_column(String(16), default="assisted")  # api|assisted
    privacy: Mapped[str] = mapped_column(String(20), default="public")
    external_id: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    platform_response: Mapped[dict[str, Any]] = mapped_column(default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    experiment_variant_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("experiment_variants.id", ondelete="SET NULL"))
    metrics_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublicationMetric(IdMixin, TimestampMixin, Base):
    """Série temporal de métricas coletadas de cada publicação."""

    __tablename__ = "publication_metrics"
    publication_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("publications.id", ondelete="CASCADE"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(20), default="api")  # api|manual
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comments: Mapped[int] = mapped_column(BigInteger, default=0)
    shares: Mapped[int] = mapped_column(BigInteger, default=0)
    saves: Mapped[int] = mapped_column(BigInteger, default=0)
    followers_gained: Mapped[int] = mapped_column(BigInteger, default=0)
    avg_watch_time_s: Mapped[float | None] = mapped_column(Float)
    completion_rate: Mapped[float | None] = mapped_column(Float)
    retention: Mapped[list[Any]] = mapped_column(default=list)
    raw: Mapped[dict[str, Any]] = mapped_column(default=dict)


class StrategyArm(IdMixin, TimestampMixin, Base):
    """Estatística agregada por combinação de dimensões (para alocação adaptativa)."""

    __tablename__ = "strategy_arms"
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    dimension: Mapped[str] = mapped_column(String(40), index=True)  # engine|visual_style|format|duration_bucket|hour|...
    value: Mapped[str] = mapped_column(String(120))
    n: Mapped[int] = mapped_column(Integer, default=0)
    mean: Mapped[float] = mapped_column(Float, default=0)
    m2: Mapped[float] = mapped_column(Float, default=0)
    ci_low: Mapped[float | None] = mapped_column(Float)
    ci_high: Mapped[float | None] = mapped_column(Float)
    reliable: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)


class OptimizationDecision(IdMixin, TimestampMixin, Base):
    __tablename__ = "optimization_decisions"
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="engine_weights")
    previous: Mapped[dict[str, Any]] = mapped_column(default=dict)
    proposed: Mapped[dict[str, Any]] = mapped_column(default=dict)
    rationale: Mapped[dict[str, Any]] = mapped_column(default=dict)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)


class Experiment(IdMixin, TimestampMixin, Base):
    __tablename__ = "experiments"
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    dimension: Mapped[str] = mapped_column(String(32))  # hook|title|cover|narration|duration|visual_style|script_format
    metric: Mapped[str] = mapped_column(String(32), default="engagement_rate")
    status: Mapped[str] = mapped_column(String(16), default="running")  # draft|running|completed|stopped
    min_samples_per_variant: Mapped[int] = mapped_column(Integer, default=10)
    confidence: Mapped[float] = mapped_column(Float, default=0.95)
    winner_variant_id: Mapped[int | None] = mapped_column(BigInteger)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperimentVariant(IdMixin, TimestampMixin, Base):
    __tablename__ = "experiment_variants"
    experiment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)  # ex.: {"hook_style":"question"} ou {"duration_s":30}
    assignments: Mapped[int] = mapped_column(Integer, default=0)
