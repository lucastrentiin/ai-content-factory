"""LLMs com API compatível com OpenAI Chat Completions: OpenAI, OpenRouter, Groq, Ollama, vLLM, LM Studio..."""
from __future__ import annotations

import time

from app.core.errors import ProviderError
from app.providers.base import LLMProvider, LLMResult, ProviderStatus, Usage
from app.providers.http import request_with_retry


class OpenAICompatibleLLM(LLMProvider):
    adapter = "openai_compatible"
    required_credentials = ()  # api_key é opcional (Ollama local não exige)
    default_model = "gpt-4o-mini"

    def status(self) -> ProviderStatus:
        if not self.config.get("base_url"):
            return ProviderStatus(False, "missing_credentials", "Defina base_url")
        if self.config.get("requires_api_key", True) and not self.credentials.get("api_key"):
            return ProviderStatus(False, "missing_credentials", "Faltam credenciais: api_key")
        return ProviderStatus(True, "configured")

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.credentials.get("api_key"):
            h["Authorization"] = f"Bearer {self.credentials['api_key']}"
        h.update(self.config.get("extra_headers", {}))
        return h

    def generate(self, *, system, prompt, model=None, max_tokens=4000, json_mode=True, effort=None, task=None):
        st = self.status()
        if not st.ok:
            raise ProviderError(st.detail, retryable=False)
        m = self.model(model)
        body = {
            "model": m,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        if json_mode and self.config.get("supports_json_mode", True):
            body["response_format"] = {"type": "json_object"}
        t0 = time.time()
        resp = request_with_retry("POST", self.config["base_url"].rstrip("/") + "/chat/completions",
                                  headers=self._headers(), json=body, timeout=self.config.get("timeout", 300))
        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise ProviderError(f"Resposta inesperada: {str(data)[:300]}", retryable=True) from e
        u = data.get("usage") or {}
        tin, tout = int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
        cost = tin / 1e6 * self.price(m, "input_per_1m_tokens") + tout / 1e6 * self.price(m, "output_per_1m_tokens")
        return LLMResult(text=text, model=data.get("model", m),
                         usage=Usage(units={"input_tokens": tin, "output_tokens": tout,
                                            "latency_ms": int((time.time() - t0) * 1000)}, cost_usd=cost))

    def healthcheck(self) -> ProviderStatus:
        st = self.status()
        if not st.ok:
            return st
        try:
            request_with_retry("GET", self.config["base_url"].rstrip("/") + "/models", headers=self._headers(), retries=0, timeout=15)
            return ProviderStatus(True, "configured", "Endpoint acessível")
        except ProviderError as e:
            return ProviderStatus(False, "error", e.message)
