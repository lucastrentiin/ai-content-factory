"""Controle de custos: registro de uso, limites (diário/mensal/canal/motor/vídeo), alertas e estimativas."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.errors import BudgetExceeded
from app.models import ApiUsage, CostLimit, ProductionJob
from app.services.common import notify


@dataclass
class CallContext:
    production_job_id: int | None = None
    channel_id: int | None = None
    engine_id: int | None = None
    agent_run_id: int | None = None
    strategy: str = "balanced"


def _period_start(period: str) -> datetime | None:
    now = datetime.now(UTC)
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "monthly":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


def spent(db: Session, *, scope: str, scope_id: int | None, period: str) -> float:
    cost = func.coalesce(func.sum(func.coalesce(ApiUsage.actual_cost_usd, ApiUsage.est_cost_usd)), 0.0)
    q = select(cost)
    start = _period_start(period)
    if start:
        q = q.where(ApiUsage.created_at >= start)
    if scope == "channel":
        q = q.where(ApiUsage.channel_id == scope_id)
    elif scope == "engine":
        q = q.where(ApiUsage.engine_id == scope_id)
    elif scope == "video":
        q = q.where(ApiUsage.production_job_id == scope_id)
    return float(db.scalar(q) or 0.0)


def applicable_limits(db: Session, ctx: CallContext) -> list[CostLimit]:
    limits = db.scalars(select(CostLimit).where(CostLimit.is_active.is_(True))).all()
    out = []
    for lim in limits:
        if lim.scope == "global" or (lim.scope == "channel" and lim.scope_id == ctx.channel_id) \
                or (lim.scope == "engine" and lim.scope_id == ctx.engine_id) \
                or (lim.scope == "video" and ctx.production_job_id is not None and (lim.scope_id in (None, ctx.production_job_id))):
            out.append(lim)
    return out


def check_budget(db: Session, ctx: CallContext, estimate_usd: float) -> None:
    """Lança BudgetExceeded se a operação ultrapassar algum limite com ação 'block'. Emite alertas no limiar."""
    if estimate_usd <= 0:
        return
    for lim in applicable_limits(db, ctx):
        sid = ctx.production_job_id if lim.scope == "video" else lim.scope_id
        period = "total" if lim.scope == "video" else lim.period
        used = spent(db, scope=lim.scope, scope_id=sid, period=period)
        label = f"{lim.scope}{'#' + str(sid) if sid else ''} ({lim.period})"
        if used + estimate_usd > lim.limit_usd and lim.action == "block":
            notify(db, "Limite de custo atingido", f"Limite {label}: US$ {used:.2f} de US$ {lim.limit_usd:.2f}. "
                   f"Operações pagas interrompidas.", level="error", category="budget",
                   dedupe_key=f"budget-block:{lim.id}:{datetime.now(UTC):%Y-%m-%d}")
            raise BudgetExceeded(f"Limite de custo {label} atingido: gasto US$ {used:.4f} + estimativa US$ {estimate_usd:.4f} "
                                 f"> US$ {lim.limit_usd:.2f}", details={"limit_id": lim.id})
        if lim.limit_usd > 0 and (used + estimate_usd) / lim.limit_usd * 100 >= lim.alert_threshold_pct:
            notify(db, "Consumo próximo do limite", f"Limite {label}: {((used + estimate_usd) / lim.limit_usd * 100):.0f}% utilizado.",
                   level="warning", category="budget", dedupe_key=f"budget-alert:{lim.id}:{datetime.now(UTC):%Y-%m-%d}")


def record_usage(db: Session, ctx: CallContext, *, provider_key: str, model_key: str | None, kind: str, operation: str,
                 units: dict, est_cost: float, actual_cost: float | None = None, duration_ms: int = 0, success: bool = True,
                 simulated: bool = False, error: str | None = None) -> ApiUsage:
    u = ApiUsage(provider_key=provider_key, model_key=model_key, kind=kind, operation=operation, units=units,
                 est_cost_usd=round(est_cost, 6), actual_cost_usd=actual_cost, production_job_id=ctx.production_job_id,
                 channel_id=ctx.channel_id, engine_id=ctx.engine_id, agent_run_id=ctx.agent_run_id,
                 duration_ms=duration_ms, success=success, is_simulated=simulated, error=error)
    db.add(u)
    if ctx.production_job_id and success:
        job = db.get(ProductionJob, ctx.production_job_id)
        if job:
            job.actual_cost_usd = round((job.actual_cost_usd or 0) + (actual_cost if actual_cost is not None else est_cost), 6)
    db.flush()
    return u


def cost_summary(db: Session, days: int = 30) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    cost = func.coalesce(func.sum(func.coalesce(ApiUsage.actual_cost_usd, ApiUsage.est_cost_usd)), 0.0)
    by_provider = db.execute(select(ApiUsage.provider_key, ApiUsage.kind, cost, func.count(), func.avg(ApiUsage.duration_ms),
                                    func.sum(case((ApiUsage.success.is_(True), 1), else_=0)))
                             .where(ApiUsage.created_at >= since).group_by(ApiUsage.provider_key, ApiUsage.kind)).all()
    by_day = db.execute(select(func.date_trunc("day", ApiUsage.created_at), cost)
                        .where(ApiUsage.created_at >= since).group_by(1).order_by(1)).all()
    by_channel = db.execute(select(ApiUsage.channel_id, cost).where(ApiUsage.created_at >= since).group_by(ApiUsage.channel_id)).all()
    by_engine = db.execute(select(ApiUsage.engine_id, cost).where(ApiUsage.created_at >= since).group_by(ApiUsage.engine_id)).all()
    jobs = db.execute(select(func.count(), func.avg(ProductionJob.actual_cost_usd)).where(
        ProductionJob.created_at >= since, ProductionJob.status == "completed")).one()
    return {
        "days": days,
        "total_usd": round(sum(r[2] for r in by_provider), 4),
        "today_usd": round(spent(db, scope="global", scope_id=None, period="daily"), 4),
        "month_usd": round(spent(db, scope="global", scope_id=None, period="monthly"), 4),
        "avg_cost_per_video_usd": round(float(jobs[1] or 0), 4),
        "videos_completed": int(jobs[0] or 0),
        "by_provider": [{"provider": p, "kind": k, "cost_usd": round(c, 4), "calls": n, "avg_ms": round(float(ms or 0)),
                         "success_rate": round((s or 0) / n, 3) if n else None} for p, k, c, n, ms, s in by_provider],
        "by_day": [{"day": d.date().isoformat(), "cost_usd": round(c, 4)} for d, c in by_day],
        "by_channel": [{"channel_id": c, "cost_usd": round(v, 4)} for c, v in by_channel],
        "by_engine": [{"engine_id": e, "cost_usd": round(v, 4)} for e, v in by_engine],
    }
