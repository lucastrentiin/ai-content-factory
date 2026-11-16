"""Verificação automática de fontes: cada fato precisa de ao menos uma fonte acessível e confiança mínima."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

MIN_CONFIDENCE = 0.7
UA = {"User-Agent": "Mozilla/5.0 (compatible; ContentFactoryFactCheck/1.0)"}


def url_ok(url: str) -> bool:
    """A fonte existe e responde (HEAD, com GET de reserva para sites que recusam HEAD)."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    try:
        with httpx.Client(timeout=10, follow_redirects=True, headers=UA) as c:
            r = c.head(url)
            if r.status_code in (403, 405, 501) or r.status_code >= 400:
                r = c.get(url)
            return r.status_code < 400
    except httpx.HTTPError:
        return False


def check_claims(claims: list[dict]) -> list[dict]:
    """Normaliza e verifica: retorna [{claim, sources, confidence, verified, note}]."""
    items = []
    for c in claims:
        srcs = c.get("sources") or ([c["source"]] if c.get("source") else [])
        srcs = [s for s in srcs if isinstance(s, str)][:3]
        try:
            conf = float(c.get("confidence", 0.8 if srcs else 0))
        except (TypeError, ValueError):
            conf = 0.0
        items.append({"claim": c.get("claim"), "sources": srcs, "confidence": conf})
    urls = sorted({u for it in items for u in it["sources"]})
    with ThreadPoolExecutor(max_workers=6) as ex:
        status = dict(zip(urls, ex.map(url_ok, urls), strict=True))
    for it in items:
        alive = [u for u in it["sources"] if status.get(u)]
        it["sources_ok"] = alive
        it["verified"] = bool(alive) and it["confidence"] >= MIN_CONFIDENCE
        it["note"] = ("Fonte acessível" if it["verified"] else
                      "Sem fonte" if not it["sources"] else
                      "Fonte inacessível ou inexistente" if not alive else "Confiança baixa")
    return items
