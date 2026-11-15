"""Analytics e aprendizado contínuo: coleta de métricas, pontuação, braços estratégicos, otimização e testes A/B."""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json
from app.core.errors import FactoryError
from app.integrations.social import get_platform
from app.models import (
    Channel,
    ChannelEngine,
    ContentEngine,
    Experiment,
    ExperimentVariant,
    OptimizationDecision,
    ProductionJob,
    Publication,
    PublicationMetric,
    SocialAccount,
    StrategyArm,
)
from app.services.common import get_setting, notify, syslog
from app.services.stats import confidence_interval, prob_best, welch_test, welford

MATURITY_HOURS = 48  # só aprende com publicações com pelo menos 48h


def engagement_score(m: PublicationMetric | dict) -> float:
    """Métrica composta: escala logarítmica de alcance × qualidade de engajamento × retenção (se disponível)."""
    g = (lambda k: getattr(m, k)) if not isinstance(m, dict) else (lambda k: m.get(k))
    views = max(0, int(g("views") or 0))
    inter = (g("likes") or 0) + 2 * (g("comments") or 0) + 3 * (g("shares") or 0) + 2 * (g("saves") or 0)
    er = inter / views if views else 0
    comp = g("completion_rate")
    retention = 0.5 + float(comp) if comp is not None else 1.0
    return round(math.log10(1 + views) * (1 + 4 * min(er, 0.5)) * retention, 4)


def metric_value(m: PublicationMetric, metric: str) -> float:
    if metric == "views":
        return float(m.views)
    if metric == "engagement_rate":
        return (m.likes + m.comments + m.shares + m.saves) / m.views if m.views else 0.0
    if metric == "completion_rate":
        return float(m.completion_rate or 0)
    if metric == "shares_rate":
        return m.shares / m.views if m.views else 0.0
    return engagement_score(m)


def latest_metrics(db: Session, channel_id: int | None = None) -> list[tuple[Publication, PublicationMetric]]:
    sub = select(PublicationMetric.publication_id, func.max(PublicationMetric.captured_at).label("mx")).group_by(PublicationMetric.publication_id).subquery()
    q = (select(Publication, PublicationMetric).join(sub, sub.c.publication_id == Publication.id)
         .join(PublicationMetric, (PublicationMetric.publication_id == sub.c.publication_id) & (PublicationMetric.captured_at == sub.c.mx)))
    if channel_id:
        q = q.where(Publication.channel_id == channel_id)
    return list(db.execute(q).all())


# ------------------------------------------------------------------------------------------- coleta
def collect_metrics(db: Session) -> dict:
    now = datetime.now(UTC)
    pubs = db.scalars(select(Publication).where(Publication.status == "published", Publication.external_id.isnot(None),
                                                Publication.mode == "api", Publication.published_at >= now - timedelta(days=45))).all()
    done, errors = 0, 0
    for p in pubs:
        age = now - p.published_at
        interval = timedelta(hours=6) if age < timedelta(days=7) else timedelta(days=1)
        if p.metrics_updated_at and now - p.metrics_updated_at < interval:
            continue
        acc = db.get(SocialAccount, p.social_account_id) if p.social_account_id else None
        if not acc or acc.status != "connected":
            continue
        try:
            from app.services.publishing import _account_creds

            m = get_platform(p.platform_key).fetch_metrics(_account_creds(db, acc), acc.config or {}, p.external_id)
        except (FactoryError, Exception) as e:  # noqa: BLE001
            errors += 1
            syslog(db, "WARNING", "analytics_agent", f"Métricas falharam pub #{p.id}: {getattr(e, 'message', str(e))[:200]}")
            continue
        db.add(PublicationMetric(publication_id=p.id, captured_at=now, source="api", views=m.views, likes=m.likes, comments=m.comments,
                                 shares=m.shares, saves=m.saves, followers_gained=m.followers_gained, avg_watch_time_s=m.avg_watch_time_s,
                                 completion_rate=m.completion_rate, raw=m.raw))
        p.metrics_updated_at = now
        done += 1
        db.commit()
    return {"collected": done, "errors": errors}


def record_manual_metrics(db: Session, pub: Publication, data: dict) -> PublicationMetric:
    m = PublicationMetric(publication_id=pub.id, captured_at=datetime.now(UTC), source="manual",
                          **{k: data.get(k) or 0 for k in ("views", "likes", "comments", "shares", "saves", "followers_gained")},
                          avg_watch_time_s=data.get("avg_watch_time_s"), completion_rate=data.get("completion_rate"), raw={"manual": True})
    db.add(m)
    pub.metrics_updated_at = m.captured_at
    db.commit()
    return m


# ------------------------------------------------------------------------------------------- agregações para o dashboard
def overview(db: Session, days: int = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = latest_metrics(db)
    recent = [(p, m) for p, m in rows if p.published_at and p.published_at >= since]
    jobs_by_status = dict(db.execute(select(ProductionJob.status, func.count()).group_by(ProductionJob.status)).all())
    produced = db.scalar(select(func.count()).select_from(ProductionJob).where(ProductionJob.output_asset_id.isnot(None),
                                                                                ProductionJob.created_at >= since)) or 0
    published = db.scalar(select(func.count()).select_from(Publication).where(Publication.status == "published",
                                                                               Publication.published_at >= since)) or 0
    scheduled = db.scalar(select(func.count()).select_from(Publication).where(Publication.status == "scheduled")) or 0
    return {
        "days": days, "videos_produced": produced, "videos_published": published, "scheduled": scheduled,
        "views": sum(m.views for _, m in recent), "likes": sum(m.likes for _, m in recent), "shares": sum(m.shares for _, m in recent),
        "comments": sum(m.comments for _, m in recent), "followers_gained": sum(m.followers_gained for _, m in recent),
        "jobs_by_status": jobs_by_status, "has_metrics": bool(rows),
    }


def breakdown(db: Session, dimension: str, channel_id: int | None = None) -> list[dict]:
    """Desempenho agregado por dimensão: engine|visual_style|format|duration_bucket|platform|hour|channel|character."""
    rows = latest_metrics(db, channel_id)
    groups: dict[str, list[tuple[Publication, PublicationMetric]]] = {}
    for p, m in rows:
        job = db.get(ProductionJob, p.production_job_id)
        if dimension == "platform":
            keys = [p.platform_key]
        elif dimension == "channel":
            keys = [db.get(Channel, p.channel_id).name]
        elif dimension == "hour":
            ch = db.get(Channel, p.channel_id)
            keys = [f"{p.published_at.astimezone(ZoneInfo(ch.timezone)).hour:02d}h"] if p.published_at else []
        elif dimension == "character":
            from app.models import Character, CharacterAppearance

            keys = [db.get(Character, a.character_id).name for a in db.scalars(select(CharacterAppearance).where(
                CharacterAppearance.production_job_id == job.id))]
        else:
            keys = [str((job.strategy or {}).get(dimension, "?"))]
        for k in keys:
            groups.setdefault(k, []).append((p, m))
    out = []
    for k, items in groups.items():
        scores = [engagement_score(m) for _, m in items]
        n, mean, m2 = welford(scores)
        lo, hi = confidence_interval(n, mean, m2)
        views = [m.views for _, m in items]
        comp = [m.completion_rate for _, m in items if m.completion_rate is not None]
        out.append({"key": k, "n": n, "score": round(mean, 3), "ci_low": lo, "ci_high": hi,
                    "avg_views": round(sum(views) / n, 1), "total_views": sum(views),
                    "avg_shares": round(sum(m.shares for _, m in items) / n, 2),
                    "avg_completion": round(sum(comp) / len(comp), 3) if comp else None})
    return sorted(out, key=lambda x: -x["score"])


def timeseries(db: Session, days: int = 30, channel_id: int | None = None) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=days)
    q = select(func.date_trunc("day", Publication.published_at), func.count()).where(Publication.status == "published",
                                                                                      Publication.published_at >= since)
    if channel_id:
        q = q.where(Publication.channel_id == channel_id)
    pubs = dict(db.execute(q.group_by(1)).all())
    views: dict = {}
    for p, m in latest_metrics(db, channel_id):
        if p.published_at and p.published_at >= since:
            d = p.published_at.replace(hour=0, minute=0, second=0, microsecond=0)
            views[d] = views.get(d, 0) + m.views
    days_list = sorted(set(pubs) | set(views))
    return [{"day": d.date().isoformat(), "published": pubs.get(d, 0), "views": views.get(d, 0)} for d in days_list]


# ------------------------------------------------------------------------------------------- aprendizado
DIMENSIONS = ("engine", "visual_style", "format", "duration_bucket", "platform", "hour")


def update_strategy_arms(db: Session, channel_id: int) -> int:
    cfg = get_setting(db, "learning")
    min_n, conf = int(cfg["min_samples"]), float(cfg["confidence"])
    cutoff = datetime.now(UTC) - timedelta(hours=MATURITY_HOURS)
    groups: dict[tuple[str, str], list[float]] = {}
    ch = db.get(Channel, channel_id)
    for p, m in latest_metrics(db, channel_id):
        if not p.published_at or p.published_at > cutoff:
            continue
        job = db.get(ProductionJob, p.production_job_id)
        s = engagement_score(m)
        strat = dict(job.strategy or {})
        strat["platform"] = p.platform_key
        strat["hour"] = f"{p.published_at.astimezone(ZoneInfo(ch.timezone)).hour:02d}h"
        for dim in DIMENSIONS:
            if strat.get(dim):
                groups.setdefault((dim, str(strat[dim])), []).append(s)
    existing = {(a.dimension, a.value): a for a in db.scalars(select(StrategyArm).where(StrategyArm.channel_id == channel_id))}
    for (dim, val), vals in groups.items():
        n, mean, m2 = welford(vals)
        lo, hi = confidence_interval(n, mean, m2, conf)
        arm = existing.get((dim, val)) or StrategyArm(channel_id=channel_id, dimension=dim, value=val)
        arm.n, arm.mean, arm.m2, arm.ci_low, arm.ci_high = n, mean, m2, lo, hi
        arm.reliable = n >= min_n
        arm.details = {"min_samples": min_n, "confidence": conf}
        db.add(arm)
    db.commit()
    return len(groups)


def optimize_channel(db: Session, channel_id: int, *, apply: bool | None = None) -> OptimizationDecision | None:
    """Ajusta pesos dos motores do canal. Só usa braços com amostra mínima; braços sem dados mantêm o peso
    (exploração). Mudanças por rodada são limitadas e há piso de exploração."""
    cfg = get_setting(db, "learning")
    ch = db.get(Channel, channel_id)
    links = db.scalars(select(ChannelEngine).where(ChannelEngine.channel_id == channel_id, ChannelEngine.is_enabled.is_(True))).all()
    if len(links) < 2:
        return None
    arms = {a.value: a for a in db.scalars(select(StrategyArm).where(StrategyArm.channel_id == channel_id, StrategyArm.dimension == "engine"))}
    keyed = {db.get(ContentEngine, link.engine_id).key: link for link in links}
    reliable = {k: (arms[k].n, arms[k].mean, arms[k].m2) for k in keyed if k in arms and arms[k].reliable}
    previous = {k: round(link.weight, 4) for k, link in keyed.items()}
    rationale: dict[str, Any] = {"reliable_arms": list(reliable), "min_samples": cfg["min_samples"]}
    if len(reliable) < 2:
        rationale["decision"] = "Dados insuficientes: pelo menos 2 motores com amostra mínima são necessários. Pesos mantidos."
        dec = OptimizationDecision(channel_id=channel_id, previous=previous, proposed=previous, rationale=rationale, applied=False)
        db.add(dec)
        db.commit()
        return dec
    pb = prob_best(reliable)
    total_w = sum(link.weight for link in keyed.values()) or 1.0
    reliable_mass = sum(keyed[k].weight for k in reliable) / total_w
    floor, maxchg = float(cfg["exploration_floor"]), float(cfg["max_weight_change"])
    proposed = {}
    for k, link in keyed.items():
        cur = link.weight / total_w
        if k in reliable:
            target = reliable_mass * (floor / len(reliable) + (1 - floor) * pb[k])
            new = cur + max(-maxchg * cur, min(maxchg * max(cur, 0.05), target - cur))
        else:
            new = cur
        new = max(link.min_share, min(link.max_share, new))
        proposed[k] = new
    s = sum(proposed.values())
    proposed = {k: round(v / s, 4) for k, v in proposed.items()}
    rationale.update({"prob_best": {k: round(v, 3) for k, v in pb.items()},
                      "means": {k: round(reliable[k][1], 3) for k in reliable},
                      "decision": "Pesos ajustados proporcionalmente à probabilidade de cada motor ser o melhor, com piso de exploração."})
    do_apply = apply if apply is not None else (ch.settings or {}).get("auto_optimize", ch.autonomy_mode == "automatic")
    dec = OptimizationDecision(channel_id=channel_id, previous=previous, proposed=proposed, rationale=rationale, applied=bool(do_apply))
    if do_apply:
        for k, w in proposed.items():
            keyed[k].weight = w
        notify(db, f"Estratégia otimizada: {ch.name}", f"Novos pesos: {proposed}", level="info", category="optimization", link="/analytics")
    db.add(dec)
    db.commit()
    return dec


def apply_decision(db: Session, dec: OptimizationDecision) -> None:
    for link in db.scalars(select(ChannelEngine).where(ChannelEngine.channel_id == dec.channel_id)):
        k = db.get(ContentEngine, link.engine_id).key
        if k in dec.proposed:
            link.weight = dec.proposed[k]
    dec.applied = True
    db.commit()


# ------------------------------------------------------------------------------------------- testes A/B
def assign_variant(db: Session, channel_id: int) -> tuple[ExperimentVariant | None, dict]:
    exp = db.scalar(select(Experiment).where(Experiment.channel_id == channel_id, Experiment.status == "running").order_by(Experiment.id))
    if not exp:
        return None, {}
    variants = db.scalars(select(ExperimentVariant).where(ExperimentVariant.experiment_id == exp.id).order_by(ExperimentVariant.assignments, ExperimentVariant.id)).all()
    if not variants:
        return None, {}
    v = variants[0]
    v.assignments += 1
    return v, {"experiment_id": exp.id, "dimension": exp.dimension, **(v.config or {})}


def evaluate_experiment(db: Session, exp: Experiment) -> dict:
    variants = db.scalars(select(ExperimentVariant).where(ExperimentVariant.experiment_id == exp.id)).all()
    data: dict[int, list[float]] = {v.id: [] for v in variants}
    cutoff = datetime.now(UTC) - timedelta(hours=MATURITY_HOURS)
    for p, m in latest_metrics(db, exp.channel_id):
        if p.experiment_variant_id in data and p.published_at and p.published_at <= cutoff:
            data[p.experiment_variant_id].append(metric_value(m, exp.metric))
    summary = {v.label: {"n": len(data[v.id]), "mean": round(sum(data[v.id]) / len(data[v.id]), 5) if data[v.id] else None} for v in variants}
    result: dict[str, Any] = {"variants": summary, "metric": exp.metric, "evaluated_at": datetime.now(UTC).isoformat()}
    enough = all(len(x) >= exp.min_samples_per_variant for x in data.values()) and len(variants) >= 2
    if not enough:
        result["conclusion"] = f"Aguardando amostra mínima de {exp.min_samples_per_variant} publicações maduras por variante."
    else:
        ranked = sorted(variants, key=lambda v: -(sum(data[v.id]) / len(data[v.id])))
        best, second = ranked[0], ranked[1]
        t = welch_test(data[best.id], data[second.id])
        result["test"] = t
        alpha = 1 - exp.confidence
        if t.get("p_value") is not None and t["p_value"] < alpha:
            exp.winner_variant_id = best.id
            exp.status = "completed"
            exp.ended_at = datetime.now(UTC)
            result["conclusion"] = f"Variante {best.label} vence com p={t['p_value']:.4f} (confiança {exp.confidence:.0%})."
            notify(db, f"Teste A/B concluído: {exp.name}", result["conclusion"], level="success", category="optimization", link="/analytics")
        else:
            result["conclusion"] = "Sem diferença estatisticamente significativa até agora."
    exp.result = result
    db.commit()
    return result
