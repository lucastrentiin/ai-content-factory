from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class TrendSource(IdMixin, TimestampMixin, Base):
    __tablename__ = "trend_sources"
    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(40))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    requires_credentials: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="idle")  # idle|ok|error|unavailable|missing_credentials
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    items_last_run: Mapped[int] = mapped_column(Integer, default=0)


class Trend(IdMixin, TimestampMixin, Base):
    __tablename__ = "trends"
    __table_args__ = (UniqueConstraint("normalized_key", "region", "language"),)
    source_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("trend_sources.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(300))
    normalized_key: Mapped[str] = mapped_column(String(300), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(8), default="BR")
    language: Mapped[str] = mapped_column(String(10), default="pt-BR")
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active|rising|declining|expired
    popularity: Mapped[dict[str, Any]] = mapped_column(default=dict)
    popularity_value: Mapped[float] = mapped_column(Float, default=0)
    score: Mapped[float] = mapped_column(Float, default=0, index=True)
    analysis: Mapped[dict[str, Any]] = mapped_column(default=dict)
    times_seen: Mapped[int] = mapped_column(Integer, default=1)
    sources_seen: Mapped[list[Any]] = mapped_column(default=list)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class TrendSnapshot(IdMixin, TimestampMixin, Base):
    __tablename__ = "trend_snapshots"
    trend_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("trends.id", ondelete="CASCADE"), index=True)
    source_key: Mapped[str | None] = mapped_column(String(60))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    popularity_value: Mapped[float] = mapped_column(Float, default=0)
    rank: Mapped[int | None] = mapped_column(Integer)
    metrics: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Idea(IdMixin, TimestampMixin, Base):
    __tablename__ = "ideas"
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    engine_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("content_engines.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("content_categories.id", ondelete="SET NULL"))
    series_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("series.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str | None] = mapped_column(String(80))
    target_audience: Mapped[str] = mapped_column(Text, default="")
    format: Mapped[str] = mapped_column(String(60), default="narrated_story")
    visual_style: Mapped[str] = mapped_column(String(60), default="stickman")
    duration_s: Mapped[int] = mapped_column(Integer, default=45)
    complexity: Mapped[int] = mapped_column(Integer, default=2)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    scores: Mapped[dict[str, Any]] = mapped_column(default=dict)
    total_score: Mapped[float] = mapped_column(Float, default=0, index=True)
    score_explanation: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    origin: Mapped[str] = mapped_column(String(20), default="generated")  # generated|manual|trend|experiment|series
    generated_by: Mapped[str | None] = mapped_column(String(120))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    dedupe_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)


class IdeaTrend(Base):
    __tablename__ = "idea_trends"
    idea_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ideas.id", ondelete="CASCADE"), primary_key=True)
    trend_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("trends.id", ondelete="CASCADE"), primary_key=True)


class Universe(IdMixin, TimestampMixin, Base):
    __tablename__ = "universes"
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    lore: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[str] = mapped_column(Text, default="")
    visual_style: Mapped[str] = mapped_column(String(60), default="stickman")
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="SET NULL"))
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)


class Series(IdMixin, TimestampMixin, Base):
    __tablename__ = "series"
    universe_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("universes.id", ondelete="SET NULL"))
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    engine_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("content_engines.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    synopsis: Mapped[str] = mapped_column(Text, default="")
    format: Mapped[str] = mapped_column(String(20), default="sequential")  # sequential|anthology|miniseries|novela
    status: Mapped[str] = mapped_column(String(20), default="active")
    episode_target: Mapped[int | None] = mapped_column(Integer)
    story_bible: Mapped[dict[str, Any]] = mapped_column(default=dict)  # arcs, themes, open_threads, tone
    visual_style: Mapped[str] = mapped_column(String(60), default="stickman")


class Episode(IdMixin, TimestampMixin, Base):
    __tablename__ = "episodes"
    __table_args__ = (UniqueConstraint("series_id", "number"),)
    series_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("series.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    synopsis: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")  # resumo pós-produção (continuidade)
    hook_next: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned|in_production|produced|published
    standalone_friendly: Mapped[bool] = mapped_column(Boolean, default=True)
    continuity: Mapped[dict[str, Any]] = mapped_column(default=dict)  # fatos estabelecidos, estados dos personagens
    production_job_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("production_jobs.id", ondelete="SET NULL", use_alter=True))
    script_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("scripts.id", ondelete="SET NULL", use_alter=True))


class Character(IdMixin, TimestampMixin, Base):
    __tablename__ = "characters"
    universe_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("universes.id", ondelete="SET NULL"), index=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    role_type: Mapped[str] = mapped_column(String(20), default="main")  # main|secondary|temporary|narrator
    identity: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    backstory: Mapped[str] = mapped_column(Text, default="")
    physical_description: Mapped[str] = mapped_column(Text, default="")
    art_style: Mapped[str] = mapped_column(String(60), default="stickman")
    # Especificação visual estruturada: rig 2D (cores, cabeça, cabelo, acessórios) + âncora de prompt + seed
    visual_spec: Mapped[dict[str, Any]] = mapped_column(default=dict)
    voice_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("voices.id", ondelete="SET NULL"))
    language: Mapped[str] = mapped_column(String(10), default="pt-BR")
    accent: Mapped[str] = mapped_column(String(60), default="")
    voice_tone: Mapped[str] = mapped_column(String(120), default="")
    speech_style: Mapped[str] = mapped_column(Text, default="")
    catchphrases: Mapped[list[Any]] = mapped_column(default=list)
    expressions: Mapped[list[Any]] = mapped_column(default=list)
    behaviors: Mapped[str] = mapped_column(Text, default="")
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_created: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    appearance_count: Mapped[int] = mapped_column(Integer, default=0)


class CharacterAsset(IdMixin, TimestampMixin, Base):
    __tablename__ = "character_assets"
    character_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24), default="reference")  # reference|turnaround|expression|sprite|preview
    label: Mapped[str] = mapped_column(String(120), default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class CharacterRelationship(IdMixin, TimestampMixin, Base):
    __tablename__ = "character_relationships"
    __table_args__ = (UniqueConstraint("character_id", "other_character_id"),)
    character_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    other_character_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("characters.id", ondelete="CASCADE"))
    relation_type: Mapped[str] = mapped_column(String(60))  # amigo, rival, irmão...
    description: Mapped[str] = mapped_column(Text, default="")
    intensity: Mapped[int] = mapped_column(Integer, default=5)


class CharacterAppearance(IdMixin, TimestampMixin, Base):
    __tablename__ = "character_appearances"
    character_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    production_job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("production_jobs.id", ondelete="CASCADE"))
    episode_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("episodes.id", ondelete="SET NULL"))
    scene_count: Mapped[int] = mapped_column(Integer, default=0)
    lines_count: Mapped[int] = mapped_column(Integer, default=0)


class Location(IdMixin, TimestampMixin, Base):
    """Cenário reutilizável (consistência visual entre vídeos)."""

    __tablename__ = "locations"
    universe_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("universes.id", ondelete="SET NULL"))
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    setting_type: Mapped[str] = mapped_column(String(40), default="room")  # chave do gerador procedural
    time_of_day: Mapped[str] = mapped_column(String(16), default="day")
    palette: Mapped[dict[str, Any]] = mapped_column(default=dict)
    visual_prompt: Mapped[str] = mapped_column(Text, default="")
    background_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    reuse_count: Mapped[int] = mapped_column(Integer, default=0)


class Voice(IdMixin, TimestampMixin, Base):
    __tablename__ = "voices"
    name: Mapped[str] = mapped_column(String(120))
    provider_key: Mapped[str] = mapped_column(String(60))
    provider_voice_id: Mapped[str] = mapped_column(String(160))
    language: Mapped[str] = mapped_column(String(10), default="pt-BR")
    accent: Mapped[str] = mapped_column(String(60), default="")
    gender: Mapped[str] = mapped_column(String(16), default="neutral")
    age_group: Mapped[str] = mapped_column(String(16), default="adult")
    description: Mapped[str] = mapped_column(Text, default="")
    # speed (0.5-2), pitch (-10..10), stability, style, default_emotion
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    sample_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    license_note: Mapped[str] = mapped_column(Text, default="")
    fallback_voice_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("voices.id", ondelete="SET NULL"))


class Asset(IdMixin, TimestampMixin, Base):
    """Arquivo no storage (S3/MinIO ou local). O banco guarda apenas a referência."""

    __tablename__ = "assets"
    kind: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    duration_s: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(20), default="generated")  # uploaded|generated|procedural|library
    provider_key: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(120))
    prompt: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str] = mapped_column(String(32), default="unknown")
    license_note: Mapped[str] = mapped_column(Text, default="")
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="SET NULL"), index=True)
    series_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("series.id", ondelete="SET NULL"))
    production_job_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("production_jobs.id", ondelete="SET NULL", use_alter=True), index=True)
    is_reusable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list[Any]] = mapped_column(default=list)
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Template(IdMixin, TimestampMixin, Base):
    """Template de edição reutilizável (legendas, transições, música, marca d'água...)."""

    __tablename__ = "templates"
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="edit")
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Script(IdMixin, TimestampMixin, Base):
    __tablename__ = "scripts"
    idea_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ideas.id", ondelete="SET NULL"), index=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    engine_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("content_engines.id", ondelete="SET NULL"))
    series_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("series.id", ondelete="SET NULL"))
    episode_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("episodes.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|review|approved|rejected
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    variant_group: Mapped[str | None] = mapped_column(String(64), index=True)
    variant_label: Mapped[str | None] = mapped_column(String(16))


class ScriptVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "script_versions"
    __table_args__ = (UniqueConstraint("script_id", "version"),)
    script_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("scripts.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    synopsis: Mapped[str] = mapped_column(Text, default="")
    full_story: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    closing: Mapped[str] = mapped_column(Text, default="")
    target_duration_s: Mapped[int] = mapped_column(Integer, default=45)
    # {"characters":[...], "locations":[...], "scenes":[...], "music":..., "fact_claims":[...]}
    content: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_by: Mapped[str] = mapped_column(String(60), default="agent")
    provider: Mapped[str | None] = mapped_column(String(120))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    review: Mapped[dict[str, Any]] = mapped_column(default=dict)
