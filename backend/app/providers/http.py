"""Helpers HTTP com retry exponencial e classificação de erros para provedores."""
from __future__ import annotations

import random
import time
from typing import Any

import httpx

from app.core.errors import ProviderError

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}


def request_with_retry(method: str, url: str, *, retries: int = 3, timeout: float = 120, base_delay: float = 1.5,
                       **kwargs: Any) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.request(method, url, timeout=timeout, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last = ProviderError(f"Falha de rede: {exc}", retryable=True)
        else:
            if resp.status_code < 400:
                return resp
            body = resp.text[:500]
            retryable = resp.status_code in RETRYABLE_STATUS
            last = ProviderError(f"HTTP {resp.status_code}: {body}", retryable=retryable,
                                 details={"status": resp.status_code})
            if not retryable:
                raise last
            ra = resp.headers.get("retry-after")
            if ra and ra.isdigit() and attempt < retries:
                time.sleep(min(int(ra), 60))
                continue
        if attempt < retries:
            time.sleep(min(base_delay * (2**attempt) + random.random(), 30))
    assert last is not None
    raise last
