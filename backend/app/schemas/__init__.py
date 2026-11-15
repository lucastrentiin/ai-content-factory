"""Schemas de entrada (validação). As respostas usam serialização direta dos modelos (sem campos sensíveis)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
HOUR = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------- auth / usuários
class LoginIn(In):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeIn(In):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class UserIn(In):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "editor", "viewer"] = "editor"


class UserUpdate(In):
    name: str | None = None
    role: Literal["admin", "editor", "viewer"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class ApiTokenIn(In):
    name: str = Field(min_length=1, max_length=120)


# ---------------------------------------------------------------- canais
class ChannelBase(In):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    identity: str | None = None
    niche: str | None = None
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    region: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    target_audience: str | None = None
    visual_style: Literal["stickman", "cartoon", "cinematic"] | None = None
    color: str | None = None
    autonomy_mode: Literal["manual", "assisted", "automatic"] | None = None
    require_approval: bool | None = None
    videos_per_day: int | None = Field(default=None, ge=0, le=50)
    preferred_hours: list[str] | None = None
    timezone: str | None = None
    default_duration_s: int | None = Field(default=None, ge=10, le=600)
    provider_strategy: Literal["quality", "cost", "balanced", "speed"] | None = None
    default_template_id: int | None = None
    platforms: list[Literal["youtube", "tiktok", "instagram"]] | None = None
    settings: dict[str, Any] | None = None
    is_active: bool | None = None

    @field_validator("preferred_hours")
    @classmethod
    def _hours(cls, v):
        if v is not None:
            for h in v:
                if not HOUR.match(h):
                    raise ValueError(f"Horário inválido: {h} (use HH:MM)")
        return v

    @field_validator("color")
    @classmethod
    def _color(cls, v):
        if v is not None and not HEX.match(v):
            raise ValueError("Cor deve ser #RRGGBB")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        if v is not None:
            from zoneinfo import ZoneInfo

            try:
                ZoneInfo(v)
            except Exception as e:  # noqa: BLE001
                raise ValueError("Fuso horário inválido") from e
        return v


class ChannelIn(ChannelBase):
    name: str = Field(min_length=1, max_length=120)
    engine_ids: list[int] = []


class ChannelEngineIn(In):
    engine_id: int
    is_enabled: bool = True
    weight: float = Field(default=1.0, ge=0, le=100)
    min_share: float = Field(default=0.05, ge=0, le=1)
    max_share: float = Field(default=0.8, ge=0, le=1)


class SocialAccountIn(In):
    platform_key: Literal["youtube", "tiktok", "instagram"]
    display_name: str = Field(min_length=1, max_length=160)
    publish_mode: Literal["api", "assisted"] = "assisted"
    config: dict[str, Any] = {}


class SocialAccountUpdate(In):
    display_name: str | None = None
    publish_mode: Literal["api", "assisted"] | None = None
    config: dict[str, Any] | None = None


# ---------------------------------------------------------------- motores
class EngineIn(In):
    key: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    engine_type: Literal["storytelling", "series", "comedy", "horror", "curiosity", "experimental", "custom"] = "custom"
    color: str = "#7c5cff"
    is_active: bool = True
    config: dict[str, Any] = {}


class EngineUpdate(In):
    name: str | None = None
    description: str | None = None
    engine_type: Literal["storytelling", "series", "comedy", "horror", "curiosity", "experimental", "custom"] | None = None
    color: str | None = None
    is_active: bool | None = None
    config: dict[str, Any] | None = None


# ---------------------------------------------------------------- tendências / ideias
class TrendImportItem(In):
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    url: str | None = None
    category: str | None = None
    popularity: float = 0


class TrendImportIn(In):
    source_key: str = "tiktok-creative-center"
    region: str = "BR"
    language: str = "pt-BR"
    items: list[TrendImportItem] = Field(min_length=1, max_length=500)


class TrendSourceUpdate(In):
    is_enabled: bool | None = None
    config: dict[str, Any] | None = None


class IdeaIn(In):
    title: str = Field(min_length=3, max_length=300)
    description: str = ""
    hook: str = ""
    channel_id: int
    engine_id: int
    series_id: int | None = None
    category: str | None = None
    target_audience: str = ""
    format: str = "narrated_story"
    visual_style: Literal["stickman", "cartoon", "cinematic"] = "cartoon"
    duration_s: int = Field(default=45, ge=10, le=600)
    trend_ids: list[int] = []
    notes: str = ""


class IdeaUpdate(In):
    title: str | None = None
    description: str | None = None
    hook: str | None = None
    format: str | None = None
    visual_style: Literal["stickman", "cartoon", "cinematic"] | None = None
    duration_s: int | None = Field(default=None, ge=10, le=600)
    status: Literal["new", "approved", "rejected", "archived"] | None = None
    notes: str | None = None
    engine_id: int | None = None


class IdeaGenerateIn(In):
    channel_id: int
    engine_id: int | None = None
    count: int = Field(default=8, ge=1, le=50)
    trend_ids: list[int] = []
    series_id: int | None = None


class ProduceIn(In):
    variants: int = Field(default=1, ge=1, le=4)
    template_id: int | None = None
    priority: int = Field(default=5, ge=1, le=10)


# ---------------------------------------------------------------- produção
class ProductionIn(In):
    channel_id: int
    engine_id: int | None = None
    idea_id: int | None = None
    title: str | None = None
    series_id: int | None = None
    episode_id: int | None = None
    template_id: int | None = None
    manual_script: dict[str, Any] | None = None
    visual_style: Literal["stickman", "cartoon", "cinematic"] | None = None
    target_duration_s: int | None = Field(default=None, ge=10, le=600)
    priority: int = Field(default=5, ge=1, le=10)
    idempotency_key: str | None = Field(default=None, max_length=120)


class RerunIn(In):
    step: str


class SceneRerenderIn(In):
    regenerate_visual: bool = False
    regenerate_audio: bool = False


class SceneEditIn(In):
    narration: str | None = None
    dialogue: list[dict[str, Any]] | None = None
    camera: str | None = None
    on_screen_text: str | None = None
    characters: list[dict[str, Any]] | None = None
    visual_description: str | None = None


class RejectIn(In):
    reason: str = ""


class ScriptVersionIn(In):
    content: dict[str, Any]
    notes: str = ""


# ---------------------------------------------------------------- universos / séries / personagens
class UniverseIn(In):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    lore: str = ""
    rules: str = ""
    visual_style: str = "cartoon"
    channel_id: int | None = None
    is_shared: bool = False


class SeriesIn(In):
    title: str = Field(min_length=1, max_length=200)
    synopsis: str = ""
    universe_id: int | None = None
    channel_id: int | None = None
    engine_id: int | None = None
    format: Literal["sequential", "anthology", "miniseries", "novela"] = "sequential"
    status: Literal["active", "paused", "finished"] = "active"
    episode_target: int | None = None
    story_bible: dict[str, Any] = {}
    visual_style: str = "cartoon"


class EpisodeIn(In):
    title: str = Field(min_length=1, max_length=200)
    synopsis: str = ""
    number: int | None = None
    standalone_friendly: bool = True


class CharacterIn(In):
    name: str = Field(min_length=1, max_length=120)
    role_type: Literal["main", "secondary", "temporary", "narrator"] = "main"
    universe_id: int | None = None
    channel_id: int | None = None
    identity: str = ""
    personality: str = ""
    backstory: str = ""
    physical_description: str = ""
    art_style: str = "cartoon"
    visual_spec: dict[str, Any] = {}
    voice_id: int | None = None
    language: str = "pt-BR"
    accent: str = ""
    voice_tone: str = ""
    speech_style: str = ""
    catchphrases: list[str] = []
    expressions: list[str] = []
    behaviors: str = ""
    is_shared: bool = False
    status: Literal["active", "archived"] = "active"


class RelationshipIn(In):
    other_character_id: int
    relation_type: str = Field(min_length=1, max_length=60)
    description: str = ""
    intensity: int = Field(default=5, ge=1, le=10)


class LocationIn(In):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    setting_type: Literal["room", "kitchen", "office", "school", "street", "city", "park", "forest", "beach", "abandoned", "lab", "space", "abstract"] = "room"
    time_of_day: Literal["day", "sunset", "night"] = "day"
    channel_id: int | None = None
    universe_id: int | None = None
    palette: dict[str, Any] = {}
    visual_prompt: str = ""


class VoiceIn(In):
    name: str = Field(min_length=1, max_length=120)
    provider_key: str
    provider_voice_id: str = Field(min_length=1, max_length=160)
    language: str = "pt-BR"
    accent: str = ""
    gender: Literal["male", "female", "neutral"] = "neutral"
    age_group: str = "adult"
    description: str = ""
    settings: dict[str, Any] = {}
    is_active: bool = True
    license_note: str = ""
    fallback_voice_id: int | None = None


class VoiceTestIn(In):
    text: str = Field(default="Olá! Esta é uma amostra da minha voz para a fábrica de conteúdo.", max_length=500)
    emotion: str = "neutral"


class TemplateIn(In):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    config: dict[str, Any] = {}
    is_default: bool = False


class AssetUpdate(In):
    name: str | None = None
    tags: list[str] | None = None
    license: Literal["internal_generated", "provider_commercial", "cc0", "user_owned", "licensed", "unknown"] | None = None
    license_note: str | None = None
    is_reusable: bool | None = None


# ---------------------------------------------------------------- publicação / analytics
class PublicationUpdate(In):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = None
    hashtags: list[str] | None = None
    scheduled_at: datetime | None = None
    privacy: Literal["public", "private", "unlisted", "friends"] | None = None
    mode: Literal["api", "assisted"] | None = None
    social_account_id: int | None = None


class ManualPublishedIn(In):
    url: str = Field(min_length=8, max_length=1000)
    external_id: str | None = None


class ManualMetricsIn(In):
    views: int = Field(ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    saves: int = Field(default=0, ge=0)
    followers_gained: int = Field(default=0, ge=0)
    avg_watch_time_s: float | None = Field(default=None, ge=0)
    completion_rate: float | None = Field(default=None, ge=0, le=1)


class ExperimentIn(In):
    channel_id: int
    name: str = Field(min_length=1, max_length=160)
    hypothesis: str = ""
    dimension: Literal["hook", "title", "cover", "narration", "duration", "visual_style", "script_format"]
    metric: Literal["engagement_score", "views", "engagement_rate", "completion_rate", "shares_rate"] = "engagement_score"
    min_samples_per_variant: int = Field(default=10, ge=3, le=1000)
    confidence: float = Field(default=0.95, ge=0.8, le=0.999)
    variants: list[dict[str, Any]] = Field(min_length=2, max_length=4)


class CostLimitIn(In):
    scope: Literal["global", "channel", "engine", "video"]
    scope_id: int | None = None
    period: Literal["daily", "monthly", "per_video"]
    limit_usd: float = Field(gt=0)
    alert_threshold_pct: float = Field(default=80, ge=1, le=100)
    action: Literal["block", "alert"] = "block"
    is_active: bool = True


class EstimateIn(In):
    channel_id: int
    engine_id: int
    duration_s: int = Field(default=45, ge=10, le=600)
    visual_style: str | None = None


# ---------------------------------------------------------------- administração
class ProviderUpdate(In):
    is_enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    config: dict[str, Any] | None = None


class ProviderCredentialsIn(In):
    credentials: dict[str, str | None]


class ProviderModelIn(In):
    model_key: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=160)
    pricing: dict[str, float] = {}
    quality_score: float = Field(default=5, ge=0, le=10)
    speed_score: float = Field(default=5, ge=0, le=10)
    is_default: bool = False
    is_enabled: bool = True


class WorkflowUpdate(In):
    is_enabled: bool | None = None
    schedule: str | None = None
    config: dict[str, Any] | None = None

    @field_validator("schedule")
    @classmethod
    def _cron(cls, v):
        if v is not None:
            from croniter import croniter

            if not croniter.is_valid(v):
                raise ValueError("Expressão cron inválida")
        return v
