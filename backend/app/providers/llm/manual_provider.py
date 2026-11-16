"""LLM em modo "copiar e colar": o usuário leva o prompt ao Claude (ou outro chat) usando a própria assinatura
e cola a resposta na plataforma. Não faz chamadas de rede; o fluxo é tratado em `providers.manual`."""
from __future__ import annotations

from app.providers.base import LLMProvider, ProviderStatus


class ManualPasteLLM(LLMProvider):
    adapter = "manual_paste"
    default_model = "claude-chat"

    def status(self) -> ProviderStatus:
        return ProviderStatus(True, "manual", "Você cola as respostas do Claude na plataforma (sem custo de API)")

    def generate(self, **kwargs):  # pragma: no cover - nunca chamado diretamente
        raise RuntimeError("O modo copiar e colar é tratado por providers.manual")
