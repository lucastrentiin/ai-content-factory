"""Claude (Anthropic) via SDK oficial `anthropic`."""
from __future__ import annotations

import time

import anthropic

from app.core.errors import ProviderError
from app.providers.base import LLMProvider, LLMResult, ProviderStatus, Usage


class AnthropicLLM(LLMProvider):
    adapter = "anthropic"
    required_credentials = ("api_key",)
    default_model = "claude-opus-5-5"

    def _client(self) -> anthropic.Anthropic:
        self.require_credentials()
        return anthropic.Anthropic(api_key=self.credentials["api_key"], max_retries=3, timeout=300.0)

    def generate(self, *, system, prompt, model=None, max_tokens=16000, json_mode=True, effort=None, task=None):
        m = self.model(model)
        sys_prompt = system
        if json_mode:
            sys_prompt += "\n\nResponda SOMENTE com um objeto JSON válido, sem texto antes ou depois e sem blocos de código."
        kwargs: dict = {
            "model": m,
            "max_tokens": max_tokens,
            "system": sys_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": effort or self.config.get("effort", "medium")},
        }
        # Fallback no servidor em caso de recusa por classificadores de segurança (modelos que suportam).
        if self.config.get("server_fallbacks", True) and m in {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
                                                               "claude-fable-5-1", "claude-fable-5-2"}:
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        t0 = time.time()
        try:
            resp = self._client().beta.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise ProviderError(f"Anthropic: chave inválida ({e.message})", retryable=False) from e
        except anthropic.PermissionDeniedError as e:
            raise ProviderError(f"Anthropic: permissão negada ({e.message})", retryable=False) from e
        except anthropic.NotFoundError as e:
            raise ProviderError(f"Anthropic: modelo/endpoint não encontrado ({e.message})", retryable=False) from e
        except anthropic.BadRequestError as e:
            raise ProviderError(f"Anthropic: requisição inválida ({e.message})", retryable=False) from e
        except anthropic.RateLimitError as e:
            raise ProviderError("Anthropic: limite de taxa atingido", retryable=True) from e
        except anthropic.APIStatusError as e:
            raise ProviderError(f"Anthropic: erro {e.status_code}", retryable=e.status_code >= 500) from e
        except anthropic.APIConnectionError as e:
            raise ProviderError("Anthropic: falha de conexão", retryable=True) from e
        if resp.stop_reason == "refusal":
            cat = getattr(getattr(resp, "stop_details", None), "category", None)
            raise ProviderError(f"Anthropic: solicitação recusada pelo modelo (categoria: {cat})", retryable=False)
        text = "".join(b.text for b in resp.content if b.type == "text")
        tin, tout = resp.usage.input_tokens, resp.usage.output_tokens
        served = resp.model or m
        cost = tin / 1e6 * self.price(served, "input_per_1m_tokens", 4.0) + tout / 1e6 * self.price(served, "output_per_1m_tokens", 20.0)
        return LLMResult(
            text=text, model=served,
            usage=Usage(units={"input_tokens": tin, "output_tokens": tout, "latency_ms": int((time.time() - t0) * 1000)}, cost_usd=cost),
            raw={"stop_reason": resp.stop_reason, "id": resp.id},
        )

    def healthcheck(self) -> ProviderStatus:
        st = self.status()
        if not st.ok:
            return st
        try:
            self._client().models.retrieve(self.model())
            return ProviderStatus(True, "configured", "Modelo acessível")
        except anthropic.AuthenticationError:
            return ProviderStatus(False, "error", "Chave de API inválida")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(False, "error", f"Falha ao verificar: {e}")
