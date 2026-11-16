"""Pesquisa de tendências: coleta, deduplicação, snapshots (evolução), status e pontuação, análise por IA."""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import FactoryError, MissingCredentials
from app.integrations.trends.sources import TrendItem, fetch, popularity_norm
from app.models import Trend, TrendSnapshot, TrendSource
from app.pipeline import prompts
from app.providers.router import ProviderRouter, llm_json
from app.services.common import syslog


def normalize_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:300]


def upsert_items(db: Session, source: TrendSource | None, items: list[TrendItem], *, region: str, language: str,
                 simulated: bool = False) -> list[Trend]:
    now = datetime.now(UTC)
    out = []
    for it in items:
        key = normalize_key(it.name)
        if not key:
            continue
        t = db.scalar(select(Trend).where(Trend.normalized_key == key, Trend.region == region, Trend.language == language))
        pop = popularity_norm(it.popularity)
        if t is None:
            t = Trend(source_id=source.id if source else None, name=it.name, normalized_key=key, description=it.description,
                      url=it.url, region=region, language=language, category=it.category, discovered_at=now, last_seen_at=now,
                      status="rising", popularity={**it.metrics, "raw": it.popularity}, popularity_value=pop,
                      sources_seen=[source.key] if source else ["manual"], is_simulated=simulated)
            db.add(t)
            db.flush()
        else:
            t.last_seen_at = now
            t.times_seen += 1
            t.popularity = {**(t.popularity or {}), **it.metrics, "raw": it.popularity}
            if source and source.key not in (t.sources_seen or []):
                t.sources_seen = [*(t.sources_seen or []), source.key]
            if it.description and not t.description:
                t.description = it.description
            prev = t.popularity_value or 0
            t.popularity_value = pop
            t.status = "rising" if pop > prev * 1.15 else ("declining" if pop < prev * 0.8 else "active")
        db.add(TrendSnapshot(trend_id=t.id, source_key=source.key if source else "manual", captured_at=now,
                             popularity_value=pop, rank=it.rank, metrics=it.metrics))
        t.score = trend_score(t)
        out.append(t)
    db.flush()
    return out


def trend_score(t: Trend) -> float:
    """0..1: popularidade, presença em várias fontes, recência, tendência de alta e potencial analisado."""
    age_h = max(0.0, (datetime.now(UTC) - (t.discovered_at or datetime.now(UTC))).total_seconds() / 3600)
    recency = math.exp(-age_h / 72)
    multi = min(1.0, len(t.sources_seen or []) / 3)
    momentum = {"rising": 1.0, "active": 0.6, "declining": 0.2, "expired": 0.0}.get(t.status, 0.5)
    potential = float((t.analysis or {}).get("potential", 0.5))
    if (t.analysis or {}).get("sensitive"):
        return 0.0
    return round(0.3 * t.popularity_value + 0.15 * multi + 0.15 * recency + 0.15 * momentum + 0.25 * potential, 4)


def research(db: Session, source_keys: list[str] | None = None) -> dict:
    sources = db.scalars(select(TrendSource).where(TrendSource.is_enabled.is_(True))).all()
    report = {}
    for src in sources:
        if source_keys and src.key not in source_keys:
            continue
        if src.source_type in ("manual_import", "tiktok_creative_center", "instagram_trends"):
            continue
        cfg = src.config or {}
        try:
            items = fetch(src.source_type, cfg)
            trends = upsert_items(db, src, items, region=cfg.get("geo", "BR"), language=cfg.get("language", "pt-BR"))
            src.status, src.last_error, src.items_last_run = "ok", None, len(trends)
            report[src.key] = {"status": "ok", "items": len(trends)}
        except MissingCredentials as e:
            src.status, src.last_error = "missing_credentials", e.message
            report[src.key] = {"status": "missing_credentials", "error": e.message}
        except (FactoryError, Exception) as e:  # noqa: BLE001
            msg = getattr(e, "message", str(e))
            src.status, src.last_error = "error", msg[:1000]
            report[src.key] = {"status": "error", "error": msg[:300]}
            syslog(db, "WARNING", "trend_researcher", f"Fonte {src.key} falhou: {msg[:300]}")
        src.last_run_at = datetime.now(UTC)
        db.commit()
    expire_old(db)
    return report


def expire_old(db: Session) -> int:
    now = datetime.now(UTC)
    n = 0
    for t in db.scalars(select(Trend).where(Trend.status != "expired", Trend.last_seen_at < now - timedelta(hours=48))):
        t.status = "expired" if t.last_seen_at < now - timedelta(days=7) else "declining"
        t.score = trend_score(t)
        n += 1
    db.commit()
    return n


def analyze(db: Session, limit: int = 25) -> dict:
    """Trend Analyst: classifica categoria, potencial, sensibilidade e formatos adaptáveis."""
    pending = db.scalars(select(Trend).where(Trend.status != "expired", Trend.analysis == {}).order_by(Trend.popularity_value.desc()).limit(limit)).all()
    if not pending:
        return {"analyzed": 0}
    if ProviderRouter(db).manual_llm():
        return {"analyzed": 0, "skipped": "Análise automática indisponível no modo copiar e colar (as tendências seguem pontuadas por popularidade)"}
    payload = [{"name": t.name, "description": t.description, "category": t.category} for t in pending]
    prompt = ("Analise as tendências a seguir para um canal de vídeos curtos brasileiro. Para cada uma retorne: category, "
              "potential (0..1, potencial para vídeos originais), why (o que torna interessante), adaptable_formats "
              "(storytelling|series|comedy|horror|curiosity|experimental), sensitive (true se tragédia, crime real, política "
              "partidária, saúde sensível, pessoas reais em situação vulnerável). Formato {\"analyses\":[{\"name\":\"\",...}]}\n"
              + str(payload))
    data, cand, simulated = llm_json(ProviderRouter(db), operation="trend_analysis", system=prompts.system_for("trend_analyst"),
                                     prompt=prompt, task={"type": "trend_analysis", "trends": payload}, max_tokens=6000)
    by_name = {a.get("name"): a for a in data.get("analyses", []) if isinstance(a, dict)}
    for t in pending:
        a = by_name.get(t.name)
        if a:
            t.analysis = {**a, "simulated": simulated, "provider": cand.rec.key}
            t.category = t.category or a.get("category")
            t.score = trend_score(t)
    db.commit()
    return {"analyzed": len(by_name), "simulated": simulated}
