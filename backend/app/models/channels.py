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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Platform(IdMixin, TimestampMixin, Base):
    """Rede social de destino e suas restrições."""

    __tablename__ = "platforms"
    key: Mapped[str] = mapped_column(String(32), unique=True)  # tiktok | instagram | youtube
    name: Mapped[str] = mapped_column(String(80))
    min_duration_s: Mapped[float] = mapped_column(Float, default=3)
    max_duration_s: Mapped[float] = mapped_column(Float, default=60)
    ideal_duration_s: Mapped[float] = mapped_column(Float, default=40)
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16")
    max_title_len: Mapped[int] = mapped_column(Integer, default=100)
    max_description_len: Mapped[int] = mapped_column(Integer, default=2200)
    max_hashtags: Mapped[int] = mapped_column(Integer, default=5)
    max_file_mb: Mapped[int] = mapped_column(Integer, default=500)
    supports_api_publish: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)


class ContentEngine(IdMixin, TimestampMixin, Base):
    """Motor de conteúdo configurável (storytelling, séries, comédia, ...)."""

    __tablename__ = "content_engines"
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    engine_type: Mapped[str] = mapped_column(String(32), default="custom")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[str] = mapped_column(String(16), default="#7c5cff")
    # editorial_rules, tone, formats, visual_styles, default_visual_mode, durations,
    # requires_fact_check, scene_count, default_voice, prompt_overrides, categories
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)


class ContentCategory(IdMixin, TimestampMixin, Base):
    __tablename__ = "content_categories"
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    engine_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("content_engines.id", ondelete="SET NULL"))
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("content_categories.id", ondelete="SET NULL"))


class Channel(IdMixin, TimestampMixin, Base):
    __tablename__ = "channels"
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    identity: Mapped[str] = mapped_column(Text, default="")
    niche: Mapped[str] = mapped_column(String(160), default="")
    language: Mapped[str] = mapped_column(String(10), default="pt-BR")
    region: Mapped[str] = mapped_column(String(8), default="BR")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    visual_style: Mapped[str] = mapped_column(String(60), default="stickman")
    color: Mapped[str] = mapped_column(String(16), default="#22d3ee")
    autonomy_mode: Mapped[str] = mapped_column(String(16), default="assisted")
    require_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    videos_per_day: Mapped[int] = mapped_column(Integer, default=1)
    preferred_hours: Mapped[list[Any]] = mapped_column(default=lambda: ["12:00", "19:00"])
    timezone: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    default_duration_s: Mapped[int] = mapped_column(Integer, default=45)
    provider_strategy: Mapped[str] = mapped_column(String(16), default="balanced")  # quality|cost|balanced|speed
    default_template_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("templates.id", ondelete="SET NULL"))
    platforms: Mapped[list[Any]] = mapped_column(default=lambda: ["youtube", "tiktok", "instagram"])
    # quality_rules, platform_overrides, hashtags_base, watermark, exploration_rate...
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    engine_links: Mapped[list[ChannelEngine]] = relationship(back_populates="channel", cascade="all, delete-orphan")


class ChannelEngine(IdMixin, TimestampMixin, Base):
    """Motores permitidos por canal + distribuição de produção (pesos ajustados pelo otimizador)."""

    __tablename__ = "channel_engines"
    __table_args__ = (UniqueConstraint("channel_id", "engine_id"),)
    channel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    engine_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("content_engines.id", ondelete="CASCADE"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    initial_weight: Mapped[float] = mapped_column(Float, default=1.0)
    weight: Mapped[float] = mapped_column(Float, default=1.0)  # peso atual (otimizado)
    min_share: Mapped[float] = mapped_column(Float, default=0.05)
    max_share: Mapped[float] = mapped_column(Float, default=0.8)

    channel: Mapped[Channel] = relationship(back_populates="engine_links")


class SocialAccount(IdMixin, TimestampMixin, Base):
    __tablename__ = "social_accounts"
    channel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    platform_key: Mapped[str] = mapped_column(String(32), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    external_account_id: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), default="disconnected")  # disconnected|connected|expired|error
    publish_mode: Mapped[str] = mapped_column(String(16), default="assisted")  # api | assisted
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[list[Any]] = mapped_column(default=list)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)  # privacy_level, app_audited, etc.
    last_error: Mapped[str | None] = mapped_column(Text)
