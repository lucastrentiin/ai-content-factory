"""Constantes de domínio (armazenadas como texto para facilitar evolução do schema)."""
from enum import StrEnum


class Role(StrEnum):
    admin = "admin"
    editor = "editor"
    viewer = "viewer"


class AutonomyMode(StrEnum):
    manual = "manual"  # usuário inicia cada etapa
    assisted = "assisted"  # produz e aguarda aprovação
    automatic = "automatic"  # produz e publica conforme regras


class IdeaStatus(StrEnum):
    new = "new"
    approved = "approved"
    rejected = "rejected"
    in_production = "in_production"
    produced = "produced"
    archived = "archived"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    paused = "paused"  # modo manual: aguarda comando para próxima etapa
    awaiting_approval = "awaiting_approval"
    needs_review = "needs_review"
    approved = "approved"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    blocked_budget = "blocked_budget"


ACTIVE_JOB_STATUSES = {JobStatus.queued, JobStatus.running}


class StepStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"
    waiting = "waiting"
    cancelled = "cancelled"


class PublicationStatus(StrEnum):
    draft = "draft"
    scheduled = "scheduled"
    publishing = "publishing"
    processing = "processing"
    published = "published"
    failed = "failed"
    awaiting_manual = "awaiting_manual"
    cancelled = "cancelled"


class ProviderKind(StrEnum):
    llm = "llm"
    image = "image"
    video = "video"
    tts = "tts"
    music = "music"
    stt = "stt"


class VisualMode(StrEnum):
    animation_2d = "animation_2d"
    ai_image = "ai_image"
    ai_video = "ai_video"


class AssetKind(StrEnum):
    image = "image"
    video = "video"
    audio = "audio"
    music = "music"
    sfx = "sfx"
    subtitle = "subtitle"
    thumbnail = "thumbnail"
    font = "font"
    other = "other"


class License(StrEnum):
    internal_generated = "internal_generated"  # gerado pela própria plataforma (procedural)
    provider_commercial = "provider_commercial"  # gerado por provedor cujos termos permitem uso comercial
    cc0 = "cc0"
    user_owned = "user_owned"
    licensed = "licensed"
    unknown = "unknown"


SAFE_LICENSES = {License.internal_generated, License.provider_commercial, License.cc0, License.user_owned, License.licensed}
