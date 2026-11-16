"""Registro de adaptadores e construção de instâncias a partir do banco (credenciais criptografadas)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_json
from app.models import ModelProvider, ProviderModel
from app.providers.base import BaseProvider
from app.providers.image.adapters import OpenAIImage, ReplicateImage, StabilityImage
from app.providers.llm.anthropic_provider import AnthropicLLM
from app.providers.llm.manual_provider import ManualPasteLLM
from app.providers.llm.openai_compatible import OpenAICompatibleLLM
from app.providers.llm.template_provider import TemplateLLM
from app.providers.music.procedural import ProceduralMusic
from app.providers.tts.adapters import ElevenLabsTTS, EspeakTTS, OpenAITTS
from app.providers.video.adapters import ReplicateVideo

ADAPTERS: dict[str, type[BaseProvider]] = {
    cls.adapter: cls
    for cls in (AnthropicLLM, OpenAICompatibleLLM, TemplateLLM, ManualPasteLLM, OpenAIImage, StabilityImage, ReplicateImage,
                ReplicateVideo, ElevenLabsTTS, OpenAITTS, EspeakTTS, ProceduralMusic)
}

# Credenciais opcionais vindas do ambiente (o banco tem precedência)
ENV_CREDENTIALS: dict[str, dict[str, str | None]] = {
    "anthropic": {"api_key": settings.anthropic_api_key},
    "openai": {"api_key": settings.openai_api_key},
    "openrouter": {"api_key": settings.openrouter_api_key},
    "openai-image": {"api_key": settings.openai_api_key},
    "openai-tts": {"api_key": settings.openai_api_key},
    "elevenlabs": {"api_key": settings.elevenlabs_api_key},
    "stability": {"api_key": settings.stability_api_key},
    "replicate-image": {"api_token": settings.replicate_api_token},
    "replicate-video": {"api_token": settings.replicate_api_token},
}
ENV_CONFIG: dict[str, dict[str, Any]] = {
    "ollama": {"base_url": settings.ollama_base_url} if settings.ollama_base_url else {},
}


def provider_credentials(rec: ModelProvider) -> dict[str, Any]:
    creds = {k: v for k, v in ENV_CREDENTIALS.get(rec.key, {}).items() if v}
    creds.update({k: v for k, v in decrypt_json(rec.credentials_encrypted).items() if v})
    return creds


def build_provider(db: Session, rec: ModelProvider) -> BaseProvider:
    cls = ADAPTERS.get(rec.adapter)
    if cls is None:
        raise ValueError(f"Adaptador desconhecido: {rec.adapter}")
    models = db.scalars(select(ProviderModel).where(ProviderModel.provider_id == rec.id)).all()
    pricing = {m.model_key: m.pricing for m in models}
    config = {**ENV_CONFIG.get(rec.key, {}), **(rec.config or {})}
    default = next((m.model_key for m in models if m.is_default and m.is_enabled), None)
    if default and not config.get("default_model"):
        config["default_model"] = default
    return cls(rec.key, provider_credentials(rec), config, pricing)
