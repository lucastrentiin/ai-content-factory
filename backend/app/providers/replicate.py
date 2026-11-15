"""Cliente mínimo da API de predições do Replicate (usado por imagem e vídeo)."""
from __future__ import annotations

import time
from typing import Any

from app.core.errors import ProviderError
from app.providers.http import request_with_retry

API = "https://api.replicate.com/v1"


def run_prediction(token: str, model: str, inputs: dict[str, Any], *, timeout_s: int = 900) -> tuple[bytes, dict]:
    headers = {"Authorization": f"Bearer {token}", "Prefer": "wait=60"}
    if ":" in model:  # versão fixada owner/name:version
        url, body = f"{API}/predictions", {"version": model.split(":", 1)[1], "input": inputs}
    else:
        url, body = f"{API}/models/{model}/predictions", {"input": inputs}
    pred = request_with_retry("POST", url, headers=headers, json=body, timeout=120).json()
    deadline = time.time() + timeout_s
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        if time.time() > deadline:
            raise ProviderError("Replicate: tempo esgotado aguardando predição", retryable=True)
        time.sleep(4)
        pred = request_with_retry("GET", pred["urls"]["get"], headers={"Authorization": f"Bearer {token}"}, timeout=60).json()
    if pred["status"] != "succeeded":
        raise ProviderError(f"Replicate: predição {pred['status']}: {pred.get('error')}", retryable=False)
    out = pred.get("output")
    if isinstance(out, list):
        out = out[0]
    if not isinstance(out, str):
        raise ProviderError(f"Replicate: saída inesperada {str(out)[:200]}", retryable=False)
    data = request_with_retry("GET", out, timeout=300).content
    return data, pred
