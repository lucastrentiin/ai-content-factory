"""Fábrica autônoma: decide o que produzir em cada canal (cotas diárias, distribuição entre motores,
séries, testes A/B) respeitando o modo de autonomia e os limites de custo."""
from __future__ import annotations

import random
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BudgetExceeded, FactoryError
from app.models import Channel, ChannelEngine, ContentEngine, Episode, ProductionJob, Series
from app.pipeline.orchestrator import create_production
from app.services.analytics import assign_variant
from app.services.common import get_setting, syslog
from app.services.costs import CallContext, check_budget
from app.services.estimate import estimate_production_cost
from app.services.ideas import best_idea, generate_ideas


def pick_engine(db: Session, channel: Channel, rng: random.Random | None = None) -> ContentEngine | None:
    rng = rng or random.Random()
    links = [link for link in db.scalars(select(ChannelEngine).where(ChannelEngine.channel_id == channel.id, ChannelEngine.is_enabled.is_(True)))
             if db.get(ContentEngine, link.engine_id).is_active]
    if not links:
        return None
    total = sum(max(0.0, link.weight) for link in links) or len(links)
    r, acc = rng.random() * total, 0.0
    for link in links:
        acc += max(0.0, link.weight) if total else 1
        if r <= acc:
            return db.get(ContentEngine, link.engine_id)
    return db.get(ContentEngine, links[-1].engine_id)


def produced_today(db: Session, channel: Channel) -> int:
    tz = ZoneInfo(channel.timezone)
    start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    return db.scalar(select(func.count()).select_from(ProductionJob).where(ProductionJob.channel_id == channel.id,
                                                                           ProductionJob.created_at >= start,
                                                                           ProductionJob.status != "cancelled")) or 0


def plan_episode(db: Session, series: Series) -> Episode:
    n = (db.scalar(select(func.max(Episode.number)).where(Episode.series_id == series.id)) or 0) + 1
    ep = Episode(series_id=series.id, number=n, title=f"{series.title} — Episódio {n}", status="planned")
    db.add(ep)
    db.flush()
    return ep


def tick(db: Session, channel_ids: list[int] | None = None) -> dict:
    auto = get_setting(db, "automation")
    if not auto.get("factory_enabled", True):
        return {"skipped": "fábrica desativada"}
    max_conc = int(auto["max_concurrent_productions"])
    active = db.scalar(select(func.count()).select_from(ProductionJob).where(ProductionJob.status.in_(["queued", "running"]))) or 0
    report = {}
    q = select(Channel).where(Channel.is_active.is_(True), Channel.autonomy_mode != "manual")
    if channel_ids:
        q = q.where(Channel.id.in_(channel_ids))
    for ch in db.scalars(q):
        if active >= max_conc:
            report[ch.slug] = "capacidade máxima de produções simultâneas"
            continue
        done = produced_today(db, ch)
        if done >= ch.videos_per_day:
            report[ch.slug] = f"cota diária atingida ({done}/{ch.videos_per_day})"
            continue
        engine = pick_engine(db, ch)
        if not engine:
            report[ch.slug] = "nenhum motor habilitado"
            continue
        est = estimate_production_cost(db, ch, engine, ch.default_duration_s, ch.visual_style)
        try:
            check_budget(db, CallContext(channel_id=ch.id, engine_id=engine.id), est["total_usd"])
        except BudgetExceeded as e:
            report[ch.slug] = f"orçamento: {e.message}"
            db.commit()
            continue
        series = None
        episode = None
        if engine.engine_type == "series":
            series = db.scalar(select(Series).where(Series.channel_id == ch.id, Series.status == "active").order_by(Series.updated_at))
            if series:
                episode = plan_episode(db, series)
        try:
            idea = None if episode else best_idea(db, ch.id, engine.id, float(auto["min_idea_score_auto"]), bool(auto["auto_approve_ideas"]))
            if not idea and not episode:
                generate_ideas(db, channel_id=ch.id, engine_id=engine.id, count=int(auto["ideas_per_run"]))
                idea = best_idea(db, ch.id, engine.id, float(auto["min_idea_score_auto"]), bool(auto["auto_approve_ideas"]))
            if not idea and not episode:
                report[ch.slug] = f"nenhuma ideia acima da nota mínima para {engine.key}"
                db.commit()
                continue
            variant, vcfg = assign_variant(db, ch.id)
            job = create_production(db, channel_id=ch.id, engine_id=engine.id, idea_id=idea.id if idea else None,
                                    series_id=series.id if series else None, episode_id=episode.id if episode else None,
                                    title=episode.title if episode else None,
                                    config={"variant": vcfg or None, "factory": True},
                                    target_duration_s=int(vcfg.get("duration_s")) if vcfg.get("duration_s") else None,
                                    visual_style=vcfg.get("visual_style"))
            if variant:
                job.experiment_variant_id = variant.id
                db.commit()
            active += 1
            report[ch.slug] = f"produção #{job.id} ({engine.key})"
        except FactoryError as e:
            db.rollback()
            report[ch.slug] = f"erro: {e.message}"
            syslog(db, "WARNING", "factory", f"Canal {ch.slug}: {e.message}")
            db.commit()
    return report
