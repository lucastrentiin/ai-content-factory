from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import editor, viewer
from app.api.utils import apply_updates, get_or_404, page, serialize
from app.core.db import get_db
from app.models import (
    ApiUsage,
    Channel,
    ContentEngine,
    CostLimit,
    Experiment,
    ExperimentVariant,
    OptimizationDecision,
    StrategyArm,
    User,
)
from app.schemas import CostLimitIn, EstimateIn, ExperimentIn
from app.services import analytics as an
from app.services.common import audit
from app.services.costs import cost_summary, spent
from app.services.estimate import estimate_production_cost
from app.worker.dispatch import enqueue

router = APIRouter(tags=["analytics", "costs"])
DIMENSIONS = {"engine", "visual_style", "format", "duration_bucket", "platform", "hour", "channel", "character"}


@router.get("/analytics/overview")
def overview(days: int = 30, db: Session = Depends(get_db), _: User = Depends(viewer)):
    return an.overview(db, days)


@router.get("/analytics/breakdown")
def breakdown(dimension: str, channel_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(viewer)):
    if dimension not in DIMENSIONS:
        raise HTTPException(422, f"Dimensão inválida; use {sorted(DIMENSIONS)}")
    return an.breakdown(db, dimension, channel_id)


@router.get("/analytics/timeseries")
def timeseries(days: int = 30, channel_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(viewer)):
    return an.timeseries(db, days, channel_id)


@router.get("/analytics/arms")
def arms(channel_id: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    return [serialize(a) for a in db.scalars(select(StrategyArm).where(StrategyArm.channel_id == channel_id)
                                             .order_by(StrategyArm.dimension, StrategyArm.mean.desc()))]


@router.post("/analytics/optimize")
def run_optimization(_: User = Depends(editor)):
    return {"task_id": enqueue("optimization", "user")}


@router.post("/analytics/collect")
def run_collect(_: User = Depends(editor)):
    return {"task_id": enqueue("collect_metrics", "user")}


@router.get("/optimization/decisions")
def decisions(channel_id: int | None = None, limit: int = 30, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(viewer)):
    q = select(OptimizationDecision)
    if channel_id:
        q = q.where(OptimizationDecision.channel_id == channel_id)
    return page(db, q.order_by(OptimizationDecision.created_at.desc()), limit=limit, offset=offset)


@router.post("/optimization/decisions/{did}/apply")
def apply_decision(did: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    d = get_or_404(db, OptimizationDecision, did, "Decisão")
    if d.applied:
        raise HTTPException(409, "Já aplicada")
    an.apply_decision(db, d)
    audit(db, "optimization.apply", user_id=user.id, entity_type="optimization_decision", entity_id=did)
    db.commit()
    return serialize(d)


# ---------------------------------------------------------------- experimentos A/B
def exp_view(db: Session, e: Experiment) -> dict:
    vs = db.scalars(select(ExperimentVariant).where(ExperimentVariant.experiment_id == e.id).order_by(ExperimentVariant.label)).all()
    return serialize(e, extra={"variants": [serialize(v) for v in vs]})


@router.get("/experiments")
def list_experiments(channel_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(viewer)):
    q = select(Experiment)
    if channel_id:
        q = q.where(Experiment.channel_id == channel_id)
    return [exp_view(db, e) for e in db.scalars(q.order_by(Experiment.created_at.desc()))]


@router.post("/experiments", status_code=201)
def create_experiment(body: ExperimentIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    get_or_404(db, Channel, body.channel_id, "Canal")
    e = Experiment(**body.model_dump(exclude={"variants"}), status="running")
    db.add(e)
    db.flush()
    for i, v in enumerate(body.variants):
        db.add(ExperimentVariant(experiment_id=e.id, label=str(v.get("label") or "ABCD"[i]), description=str(v.get("description", "")),
                                 config=v.get("config") or {}))
    audit(db, "experiment.create", user_id=user.id, entity_type="experiment", entity_id=e.id)
    db.commit()
    return exp_view(db, e)


@router.post("/experiments/{eid}/evaluate")
def evaluate(eid: int, db: Session = Depends(get_db), _: User = Depends(editor)):
    e = get_or_404(db, Experiment, eid, "Experimento")
    an.evaluate_experiment(db, e)
    return exp_view(db, e)


@router.post("/experiments/{eid}/stop")
def stop(eid: int, db: Session = Depends(get_db), _: User = Depends(editor)):
    e = get_or_404(db, Experiment, eid, "Experimento")
    e.status = "stopped"
    db.commit()
    return exp_view(db, e)


# ---------------------------------------------------------------- custos
@router.get("/costs/summary")
def costs(days: int = 30, db: Session = Depends(get_db), _: User = Depends(viewer)):
    data = cost_summary(db, days)
    names = {c.id: c.name for c in db.scalars(select(Channel))}
    engines = {e.id: e.name for e in db.scalars(select(ContentEngine))}
    for r in data["by_channel"]:
        r["name"] = names.get(r["channel_id"], "Sem canal")
    for r in data["by_engine"]:
        r["name"] = engines.get(r["engine_id"], "Sem motor")
    data["cost_per_1k_views"] = None
    ov = an.overview(db, days)
    if ov["views"]:
        data["cost_per_1k_views"] = round(data["total_usd"] / ov["views"] * 1000, 4)
    return data


@router.get("/costs/usage")
def usage(provider: str | None = None, kind: str | None = None, production_job_id: int | None = None, limit: int = 100, offset: int = 0,
          db: Session = Depends(get_db), _: User = Depends(viewer)):
    q = select(ApiUsage)
    if provider:
        q = q.where(ApiUsage.provider_key == provider)
    if kind:
        q = q.where(ApiUsage.kind == kind)
    if production_job_id:
        q = q.where(ApiUsage.production_job_id == production_job_id)
    return page(db, q.order_by(ApiUsage.created_at.desc()), limit=limit, offset=offset)


@router.get("/costs/limits")
def limits(db: Session = Depends(get_db), _: User = Depends(viewer)):
    out = []
    for lim in db.scalars(select(CostLimit).order_by(CostLimit.scope, CostLimit.period)):
        used = None if lim.scope == "video" else spent(db, scope=lim.scope, scope_id=lim.scope_id, period=lim.period)
        out.append(serialize(lim, extra={"used_usd": round(used, 4) if used is not None else None,
                                         "used_pct": round(used / lim.limit_usd * 100, 1) if used is not None and lim.limit_usd else None}))
    return out


@router.post("/costs/limits", status_code=201)
def create_limit(body: CostLimitIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    if body.scope in ("channel", "engine") and not body.scope_id:
        raise HTTPException(422, "Informe scope_id")
    lim = CostLimit(**body.model_dump())
    db.add(lim)
    audit(db, "cost_limit.create", user_id=user.id, data=body.model_dump())
    db.commit()
    return serialize(lim)


@router.patch("/costs/limits/{lid}")
def update_limit(lid: int, body: CostLimitIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    lim = apply_updates(get_or_404(db, CostLimit, lid, "Limite"), body.model_dump(exclude_unset=True))
    audit(db, "cost_limit.update", user_id=user.id, entity_type="cost_limit", entity_id=lid)
    db.commit()
    return serialize(lim)


@router.delete("/costs/limits/{lid}", status_code=204)
def delete_limit(lid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    db.delete(get_or_404(db, CostLimit, lid, "Limite"))
    audit(db, "cost_limit.delete", user_id=user.id, entity_type="cost_limit", entity_id=lid)
    db.commit()


@router.post("/costs/estimate")
def estimate(body: EstimateIn, db: Session = Depends(get_db), _: User = Depends(viewer)):
    ch = get_or_404(db, Channel, body.channel_id, "Canal")
    eng = get_or_404(db, ContentEngine, body.engine_id, "Motor")
    return estimate_production_cost(db, ch, eng, body.duration_s, body.visual_style)
