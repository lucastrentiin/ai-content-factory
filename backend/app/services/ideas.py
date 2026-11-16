"""Motor de ideias: geração (LLM), deduplicação, avaliação multicritério com histórico de desempenho, seleção."""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Channel, ChannelEngine, ContentEngine, Idea, IdeaTrend, Series, StrategyArm, Trend
from app.pipeline import prompts
from app.pipeline.orchestrator import duration_bucket
from app.providers.router import ProviderRouter, llm_json
from app.services.costs import CallContext
from app.services.estimate import estimate_production_cost
from app.services.trends import normalize_key

DEFAULT_WEIGHTS = {"attention": 0.2, "retention": 0.18, "shareability": 0.14, "originality": 0.1, "trend_fit": 0.1,
                   "production_ease": 0.1, "continuation": 0.06, "historical": 0.12}


def idea_hash(channel_id: int | None, title: str) -> str:
    return hashlib.sha256(f"{channel_id}|{normalize_key(title)}".encode()).hexdigest()


def history_summary(db: Session, channel_id: int) -> dict[str, Any]:
    arms = db.scalars(select(StrategyArm).where(StrategyArm.channel_id == channel_id, StrategyArm.n > 0)).all()
    if not arms:
        return {"note": "Sem dados de desempenho ainda — explore formatos variados."}
    out: dict[str, list] = {}
    for a in arms:
        out.setdefault(a.dimension, []).append({"value": a.value, "n": a.n, "mean_score": round(a.mean, 3), "reliable": a.reliable})
    for k in out:
        out[k].sort(key=lambda x: -x["mean_score"])
    return out


def historical_score(db: Session, channel_id: int | None, dims: dict[str, str]) -> tuple[float, dict]:
    """0..1 a partir de braços confiáveis (amostra mínima); 0.5 quando não há dados suficientes."""
    if not channel_id:
        return 0.5, {"reason": "sem canal"}
    arms = {(a.dimension, a.value): a for a in db.scalars(select(StrategyArm).where(StrategyArm.channel_id == channel_id))}
    all_means = [a.mean for a in arms.values() if a.reliable]
    if not all_means:
        return 0.5, {"reason": "dados insuficientes"}
    lo, hi = min(all_means), max(all_means)
    parts, used = [], {}
    for dim, val in dims.items():
        a = arms.get((dim, str(val)))
        if a and a.reliable:
            v = 0.5 if hi == lo else (a.mean - lo) / (hi - lo)
            parts.append(v)
            used[dim] = {"value": val, "n": a.n, "norm": round(v, 3)}
    if not parts:
        return 0.5, {"reason": "sem braços confiáveis para estas dimensões"}
    return round(sum(parts) / len(parts), 4), used


def generate_ideas(db: Session, *, channel_id: int, engine_id: int | None = None, count: int = 8, trend_ids: list[int] | None = None,
                   series_id: int | None = None) -> list[Idea]:
    channel = db.get(Channel, channel_id)
    if engine_id is None:
        link = db.scalar(select(ChannelEngine).where(ChannelEngine.channel_id == channel_id, ChannelEngine.is_enabled.is_(True))
                         .order_by(ChannelEngine.weight.desc()))
        engine_id = link.engine_id if link else None
    engine = db.get(ContentEngine, engine_id)
    if not engine:
        raise ValueError("Motor não encontrado")
    q = select(Trend).where(Trend.status != "expired", Trend.region == channel.region, Trend.score > 0)
    if trend_ids:
        q = select(Trend).where(Trend.id.in_(trend_ids))
    trends = db.scalars(q.order_by(Trend.score.desc()).limit(12)).all()
    tr_payload = [{"name": t.name, "category": t.category, "why": (t.analysis or {}).get("why")} for t in trends
                  if not (t.analysis or {}).get("adaptable_formats") or engine.engine_type in t.analysis["adaptable_formats"]
                  or engine.engine_type in ("experimental", "custom")][:8] or [{"name": t.name, "category": t.category} for t in trends[:5]]
    series = db.get(Series, series_id) if series_id else None
    ch = {"name": channel.name, "niche": channel.niche, "target_audience": channel.target_audience,
          "visual_style": channel.visual_style, "default_duration_s": channel.default_duration_s}
    router = ProviderRouter(db, CallContext(channel_id=channel.id, engine_id=engine.id, strategy=channel.provider_strategy))
    data, cand, simulated = llm_json(
        router, operation="generate_ideas",
        system=prompts.system_for("idea_generator", language=channel.language, region=channel.region,
                                  engine={"name": engine.name, "engine_type": engine.engine_type, "description": engine.description, "config": engine.config}),
        prompt=prompts.ideas_prompt(channel=ch, engine={"name": engine.name}, trends=tr_payload, count=count,
                                    history=history_summary(db, channel.id), series={"title": series.title, "synopsis": series.synopsis} if series else None),
        task={"type": "ideas", "engine_type": engine.engine_type, "trends": tr_payload, "count": count, "niche": channel.niche,
              "visual_style": channel.visual_style, "target_duration_s": channel.default_duration_s, "audience": channel.target_audience,
              "series_title": series.title if series else None, "seed": str(db.scalar(select(Idea.id).order_by(Idea.id.desc()).limit(1)) or 0)},
        max_tokens=8000, agent="idea_generator",
        resume={"kind": "generate_ideas", "params": {"channel_id": channel_id, "engine_id": engine.id, "count": count,
                                                      "trend_ids": trend_ids, "series_id": series_id}})
    created = []
    trend_by_name = {t.name: t for t in trends}
    for raw in data.get("ideas", [])[:count]:
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        h = idea_hash(channel.id, title)
        if db.scalar(select(Idea.id).where(Idea.dedupe_hash == h)):
            continue
        style = raw.get("visual_style") if raw.get("visual_style") in ("stickman", "cartoon", "cinematic") else channel.visual_style
        idea = Idea(channel_id=channel.id, engine_id=engine.id, series_id=series_id, title=title[:300],
                    description=str(raw.get("description") or ""), hook=str(raw.get("hook") or ""), category=raw.get("category"),
                    target_audience=str(raw.get("target_audience") or channel.target_audience), format=str(raw.get("format") or "narrated_story")[:60],
                    visual_style=style, duration_s=int(raw.get("duration_s") or channel.default_duration_s),
                    origin="series" if series_id else ("trend" if raw.get("trend") else "generated"),
                    generated_by=f"{cand.rec.key}:{cand.model_key}", is_simulated=simulated, dedupe_hash=h,
                    data={"protagonist": raw.get("protagonist"), "trend": raw.get("trend"),
                          "continuation_potential": raw.get("continuation_potential"),
                          "self_scores": {k: raw[k] for k in ("attention", "retention", "shareability", "originality") if k in raw}})
        db.add(idea)
        db.flush()
        t = trend_by_name.get(raw.get("trend"))
        if t:
            db.add(IdeaTrend(idea_id=idea.id, trend_id=t.id))
        created.append(idea)
    db.flush()
    if created:
        evaluate_ideas(db, created, router=router)
    db.commit()
    return created


def evaluate_ideas(db: Session, ideas: list[Idea], *, router: ProviderRouter | None = None) -> None:
    if not ideas:
        return
    channel = db.get(Channel, ideas[0].channel_id) if ideas[0].channel_id else None
    router = router or ProviderRouter(db)
    payload = [{"title": i.title, "description": i.description, "hook": i.hook, "format": i.format} for i in ideas]
    if router.manual_llm():  # copiar e colar: usa a autoavaliação que veio junto com as ideias (sem segundo colar)
        evals = {k: {**(i.data or {}).get("self_scores", {}), "rationale": "Autoavaliação do Claude (modo copiar e colar)"} for k, i in enumerate(ideas)}
        simulated = False
    else:
      try:
        data, cand, simulated = llm_json(router, operation="evaluate_ideas", system=prompts.system_for("idea_evaluator"),
                                         prompt=prompts.evaluate_prompt(payload, {"name": channel.name if channel else "", "niche": channel.niche if channel else ""}),
                                         task={"type": "evaluate_ideas", "ideas": payload}, max_tokens=4000)
        evals = {int(e.get("index", -1)): e for e in data.get("evaluations", []) if isinstance(e, dict)}
      except Exception:  # noqa: BLE001 — avaliação heurística mesmo sem LLM
        evals, simulated = {}, True
    weights = {**DEFAULT_WEIGHTS, **((channel.settings or {}).get("idea_weights", {}) if channel else {})}
    for i, idea in enumerate(ideas):
        e = evals.get(i, {})
        engine = db.get(ContentEngine, idea.engine_id)
        est = estimate_production_cost(db, channel, engine, idea.duration_s, idea.visual_style) if channel else {"total_usd": 0}
        trend_fit = 0.0
        links = db.scalars(select(IdeaTrend.trend_id).where(IdeaTrend.idea_id == idea.id)).all()
        if links:
            trend_fit = max((db.get(Trend, t).score for t in links), default=0.0)
        complexity = 1 + (1 if idea.visual_style == "cinematic" else 0) + (1 if idea.format in ("episode", "documentary") else 0)
        hist, hist_info = historical_score(db, idea.channel_id, {"engine": engine.key, "format": idea.format,
                                                                  "visual_style": idea.visual_style, "duration_bucket": duration_bucket(idea.duration_s)})
        scores = {
            "attention": _f(e.get("attention"), 0.5), "retention": _f(e.get("retention"), 0.5),
            "shareability": _f(e.get("shareability"), 0.5), "originality": _f(e.get("originality"), 0.5),
            "trend_fit": round(trend_fit, 3), "production_ease": round(1 - (complexity - 1) / 3, 3),
            "continuation": _f((idea.data or {}).get("continuation_potential"), 0.3), "historical": hist,
        }
        total = sum(scores[k] * w for k, w in weights.items()) / sum(weights.values())
        idea.scores = scores
        idea.total_score = round(total, 4)
        idea.complexity = complexity
        idea.est_cost_usd = est["total_usd"]
        idea.score_explanation = {"weights": weights, "rationale": e.get("rationale"), "historical": hist_info,
                                  "llm_simulated": simulated, "cost_breakdown": est.get("breakdown")}
    db.flush()


def _f(v: Any, default: float) -> float:
    try:
        return round(max(0.0, min(1.0, float(v))), 3)
    except (TypeError, ValueError):
        return default


def best_idea(db: Session, channel_id: int, engine_id: int, min_score: float, auto_approve: bool) -> Idea | None:
    statuses = ["approved", "new"] if auto_approve else ["approved"]
    idea = db.scalar(select(Idea).where(Idea.channel_id == channel_id, Idea.engine_id == engine_id, Idea.status.in_(statuses),
                                        Idea.total_score >= min_score).order_by(Idea.status == "new", Idea.total_score.desc()).limit(1))
    if idea and idea.status == "new":
        idea.status = "approved"
    return idea
