from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class ProductionJob(IdMixin, TimestampMixin, Base):
    """Uma produção de vídeo (execução do pipeline de agentes)."""

    __tablename__ = "production_jobs"
    channel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    engine_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("content_engines.id", ondelete="RESTRICT"), index=True)
    idea_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ideas.id", ondelete="SET NULL"))
    script_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("scripts.id", ondelete="SET NULL"))
    series_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("series.id", ondelete="SET NULL"))
    episode_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("episodes.id", ondelete="SET NULL"))
    template_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("templates.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    autonomy_mode: Mapped[str] = mapped_column(String(16), default="assisted")
    current_step: Mapped[str | None] = mapped_column(String(40))
    progress: Mapped[float] = mapped_column(Float, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    visual_style: Mapped[str] = mapped_column(String(60), default="stickman")
    format: Mapped[str] = mapped_column(String(60), default="narrated_story")
    target_duration_s: Mapped[int] = mapped_column(Integer, default=45)
    output_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    thumbnail_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    actual_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    qc_report: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    is_simulated: Mapped[bool] = mapped_column(default=False)
    simulated_parts: Mapped[list[Any]] = mapped_column(default=list)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    # dimensões usadas no aprendizado (engine, visual_style, format, duration_bucket, hook_style)
    strategy: Mapped[dict[str, Any]] = mapped_column(default=dict)
    experiment_variant_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("experiment_variants.id", ondelete="SET NULL"))
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    approved_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRun(IdMixin, TimestampMixin, Base):
    """Execução rastreável de um agente/etapa: entrada, saída, status, erros, tentativas, custo."""

    __tablename__ = "agent_runs"
    agent: Mapped[str] = mapped_column(String(40), index=True)
    production_job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    step_order: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    input: Mapped[dict[str, Any]] = mapped_column(default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(40))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    providers_used: Mapped[list[Any]] = mapped_column(default=list)
    events: Mapped[list[Any]] = mapped_column(default=list)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="SET NULL"), index=True)
    triggered_by: Mapped[str] = mapped_column(String(40), default="system")


class Scene(IdMixin, TimestampMixin, Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("production_job_id", "index"),)
    production_job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), default="")
    duration_s: Mapped[float] = mapped_column(Float, default=4)
    narration: Mapped[str] = mapped_column(Text, default="")
    dialogue: Mapped[list[Any]] = mapped_column(default=list)  # [{character, text, emotion, action}]
    characters: Mapped[list[Any]] = mapped_column(default=list)  # [{character_id, name, action, expression, position}]
    location_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("locations.id", ondelete="SET NULL"))
    location_name: Mapped[str] = mapped_column(String(160), default="")
    visual_description: Mapped[str] = mapped_column(Text, default="")
    emotion: Mapped[str] = mapped_column(String(40), default="neutral")
    visual_mode: Mapped[str] = mapped_column(String(20), default="animation_2d")
    camera: Mapped[str] = mapped_column(String(30), default="static")
    transition: Mapped[str] = mapped_column(String(30), default="cut")
    sfx: Mapped[list[Any]] = mapped_column(default=list)
    music_cue: Mapped[str] = mapped_column(String(60), default="")
    on_screen_text: Mapped[str] = mapped_column(Text, default="")
    plan: Mapped[dict[str, Any]] = mapped_column(default=dict)  # saída do Scene Planner
    audio_timeline: Mapped[list[Any]] = mapped_column(default=list)  # [{start,end,speaker,text,asset_id}]
    status: Mapped[str] = mapped_column(String(16), default="pending")
    spec_hash: Mapped[str | None] = mapped_column(String(64))
    clip_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    audio_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    image_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    video_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    error: Mapped[str | None] = mapped_column(Text)
    needs_rerender: Mapped[bool] = mapped_column(default=False)


class RenderJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "render_jobs"
    production_job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("scenes.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))  # scene_clip|final|thumbnail
    status: Mapped[str] = mapped_column(String(16), default="pending")
    progress: Mapped[float] = mapped_column(Float, default=0)
    output_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    cached: Mapped[bool] = mapped_column(default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
