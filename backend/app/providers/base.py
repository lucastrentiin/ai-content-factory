"""Contratos dos provedores (LLM, imagem, vídeo, TTS, música).

Cada adaptador é independente de fornecedor; o roteador (router.py) escolhe o provedor com base em
prioridade, estratégia do canal (qualidade/custo/velocidade), disponibilidade e limites de custo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.core.errors import MissingCredentials


@dataclass
class ProviderStatus:
    ok: bool
    status: str  # configured | missing_credentials | unavailable | simulated | error | disabled
    detail: str = ""


@dataclass
class Usage:
    units: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    actual_cost_usd: float | None = None


@dataclass
class LLMResult:
    text: str
    model: str
    usage: Usage
    simulated: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageResult:
    data: bytes
    mime: str
    model: str
    usage: Usage
    seed: int | None = None
    simulated: bool = False


@dataclass
class VideoResult:
    data: bytes
    mime: str
    model: str
    usage: Usage
    duration_s: float | None = None


@dataclass
class TTSResult:
    data: bytes
    mime: str  # audio/wav | audio/mpeg
    model: str
    usage: Usage
    word_timings: list[dict[str, Any]] | None = None
    simulated: bool = False


@dataclass
class MusicResult:
    data: bytes
    mime: str
    model: str
    usage: Usage
    license: str = "internal_generated"


class BaseProvider:
    """Classe base. `credentials` vem descriptografado do banco ou das variáveis de ambiente."""

    kind: ClassVar[str] = ""
    adapter: ClassVar[str] = ""
    simulated: ClassVar[bool] = False
    required_credentials: ClassVar[tuple[str, ...]] = ()
    default_model: ClassVar[str] = ""

    def __init__(self, key: str, credentials: dict[str, Any] | None = None, config: dict[str, Any] | None = None,
                 pricing: dict[str, dict[str, Any]] | None = None):
        self.key = key
        self.credentials = credentials or {}
        self.config = config or {}
        # pricing por modelo: {"model": {"input_per_1m_tokens": 3, ...}}
        self.pricing = pricing or {}

    # ---- configuração
    def missing_credentials(self) -> list[str]:
        return [c for c in self.required_credentials if not self.credentials.get(c)]

    def status(self) -> ProviderStatus:
        missing = self.missing_credentials()
        if missing:
            return ProviderStatus(False, "missing_credentials", "Faltam credenciais: " + ", ".join(missing))
        if self.simulated:
            return ProviderStatus(True, "simulated", "Provedor simulado/local (sem custo, qualidade limitada)")
        return ProviderStatus(True, "configured", "")

    def require_credentials(self) -> None:
        missing = self.missing_credentials()
        if missing:
            raise MissingCredentials(f"Provedor {self.key}: faltam credenciais {', '.join(missing)}")

    def model(self, override: str | None = None) -> str:
        return override or self.config.get("default_model") or self.default_model

    def price(self, model: str, unit: str, default: float = 0.0) -> float:
        p = self.pricing.get(model) or self.pricing.get("*") or {}
        return float(p.get(unit, default))

    def healthcheck(self) -> ProviderStatus:
        """Verificação leve (sem custo). Adaptadores podem sobrescrever com chamada real a endpoint gratuito."""
        return self.status()


class LLMProvider(BaseProvider):
    kind = "llm"

    def generate(self, *, system: str, prompt: str, model: str | None = None, max_tokens: int = 4000,
                 json_mode: bool = True, effort: str | None = None, task: dict[str, Any] | None = None) -> LLMResult:
        """`task` descreve a tarefa estruturada (usada apenas pelo provedor simulado; LLMs reais usam o prompt)."""
        raise NotImplementedError

    def estimate_cost(self, *, prompt_chars: int, max_tokens: int, model: str | None = None) -> float:
        m = self.model(model)
        tin = prompt_chars / 3.5
        return tin / 1e6 * self.price(m, "input_per_1m_tokens") + max_tokens * 0.6 / 1e6 * self.price(m, "output_per_1m_tokens")


class ImageProvider(BaseProvider):
    kind = "image"

    def generate(self, *, prompt: str, width: int, height: int, seed: int | None = None,
                 negative_prompt: str | None = None, reference_images: list[bytes] | None = None,
                 model: str | None = None) -> ImageResult:
        raise NotImplementedError

    def estimate_cost(self, *, count: int = 1, model: str | None = None) -> float:
        return count * self.price(self.model(model), "per_image")


class VideoProvider(BaseProvider):
    kind = "video"

    def generate(self, *, prompt: str, duration_s: float, image: bytes | None = None, aspect_ratio: str = "9:16",
                 model: str | None = None) -> VideoResult:
        raise NotImplementedError

    def estimate_cost(self, *, duration_s: float, model: str | None = None) -> float:
        m = self.model(model)
        return self.price(m, "per_second") * duration_s + self.price(m, "per_video")


class TTSProvider(BaseProvider):
    kind = "tts"

    def synthesize(self, *, text: str, voice_id: str, language: str = "pt-BR", speed: float = 1.0,
                   pitch: float = 0.0, emotion: str | None = None, settings: dict[str, Any] | None = None,
                   model: str | None = None) -> TTSResult:
        raise NotImplementedError

    def estimate_cost(self, *, chars: int, model: str | None = None) -> float:
        return chars / 1000 * self.price(self.model(model), "per_1k_chars")

    def list_voices(self) -> list[dict[str, Any]]:
        return []


class MusicProvider(BaseProvider):
    kind = "music"

    def generate(self, *, mood: str, duration_s: float, bpm: int | None = None, seed: int | None = None,
                 model: str | None = None) -> MusicResult:
        raise NotImplementedError

    def estimate_cost(self, *, duration_s: float, model: str | None = None) -> float:
        return self.price(self.model(model), "per_second") * duration_s
