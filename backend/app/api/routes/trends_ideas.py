from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import editor, viewer
from app.api.utils import apply_updates, get_or_404, page, serialize
from app.core.db import get_db
from app.integrations.trends.sources import TrendItem
from app.models import (
    Channel,
    ContentEngine,
    Idea,
    IdeaTrend,
    ProductionJob,
    Trend,
    TrendSnapshot,
    TrendSource,
    User,
)
from app.pipeline.orchestrator import create_production
from app.schemas import IdeaGenerateIn, IdeaIn, IdeaUpdate, ProduceIn, TrendImportIn, TrendSourceUpdate
from app.services import ideas as ideas_svc
from app.services import trends as trends_svc
from app.services.common import audit
from app.worker.dispatch import enqueue

router = APIRouter(tags=["trends", "ideas"])


# ---------------------------------------------------------------- tendências
@router.get("/trends")
def list_trends(status: str | None = None, category: str | None = None, source_id: int | None = None, region: str | None = None,
                q: str | None = None, sort: str = "score", limit: int = 50, offset: int = 0,
                db: Session = Depends(get_db), _: User = Depends(viewer)):
    query = select(Trend)
    if status:
        query = query.where(Trend.status == status)
    if category:
        query = query.where(Trend.category == category)
    if source_id:
        query = query.where(Trend.source_id == source_id)
    if region:
        query = query.where(Trend.region == region)
    if q:
        query = query.where(or_(Trend.name.ilike(f"%{q}%"), Trend.description.ilike(f"%{q}%")))
    order = {"score": Trend.score.desc(), "recent": Trend.discovered_at.desc(), "popularity": Trend.popularity_value.desc()}.get(sort, Trend.score.desc())
    return page(db, query.order_by(order), limit=limit, offset=offset)


@router.get("/trends/categories")
def trend_categories(db: Session = Depends(get_db), _: User = Depends(viewer)):
    return [c for c in db.scalars(select(Trend.category).where(Trend.category.isnot(None)).distinct()).all()]


@router.get("/trends/{tid}")
def get_trend(tid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    t = get_or_404(db, Trend, tid, "Tendência")
    snaps = db.scalars(select(TrendSnapshot).where(TrendSnapshot.trend_id == tid).order_by(TrendSnapshot.captured_at)).all()
    idea_ids = db.scalars(select(IdeaTrend.idea_id).where(IdeaTrend.trend_id == tid)).all()
    ideas = db.scalars(select(Idea).where(Idea.id.in_(idea_ids))).all() if idea_ids else []
    src = db.get(TrendSource, t.source_id) if t.source_id else None
    return serialize(t, extra={"snapshots": [serialize(s) for s in snaps], "ideas": [serialize(i) for i in ideas],
                               "source": serialize(src) if src else None})


@router.post("/trends/research")
def run_research(body: dict | None = None, _: User = Depends(editor)):
    task_id = enqueue("trend_research", (body or {}).get("source_keys"), "user")
    return {"queued": True, "task_id": task_id}


@router.post("/trends/import")
def import_trends(body: TrendImportIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    src = db.scalar(select(TrendSource).where(TrendSource.key == body.source_key))
    items = [TrendItem(name=i.name, description=i.description, url=i.url, category=i.category, popularity=i.popularity,
                       metrics={"imported": True}) for i in body.items]
    trends = trends_svc.upsert_items(db, src, items, region=body.region, language=body.language)
    if src:
        src.status, src.items_last_run = "ok", len(trends)
    audit(db, "trends.import", user_id=user.id, data={"source": body.source_key, "count": len(trends)})
    db.commit()
    return {"imported": len(trends)}


@router.post("/trends/analyze")
def analyze_trends(db: Session = Depends(get_db), _: User = Depends(editor)):
    return trends_svc.analyze(db)


@router.delete("/trends/{tid}", status_code=204)
def delete_trend(tid: int, db: Session = Depends(get_db), _: User = Depends(editor)):
    db.delete(get_or_404(db, Trend, tid, "Tendência"))
    db.commit()


@router.get("/trend-sources")
def list_sources(db: Session = Depends(get_db), _: User = Depends(viewer)):
    return [serialize(s) for s in db.scalars(select(TrendSource).order_by(TrendSource.id))]


@router.patch("/trend-sources/{sid}")
def update_source(sid: int, body: TrendSourceUpdate, db: Session = Depends(get_db), _: User = Depends(editor)):
    s = get_or_404(db, TrendSource, sid, "Fonte")
    data = body.model_dump(exclude_unset=True)
    if data.get("config") is not None:
        data["config"] = {**(s.config or {}), **data["config"]}
    apply_updates(s, data)
    db.commit()
    return serialize(s)


# ---------------------------------------------------------------- ideias
def idea_view(db: Session, i: Idea) -> dict:
    tids = db.scalars(select(IdeaTrend.trend_id).where(IdeaTrend.idea_id == i.id)).all()
    trends = db.scalars(select(Trend).where(Trend.id.in_(tids))).all() if tids else []
    jobs = db.scalars(select(ProductionJob.id).where(ProductionJob.idea_id == i.id)).all()
    eng = db.get(ContentEngine, i.engine_id)
    return serialize(i, extra={"trends": [{"id": t.id, "name": t.name} for t in trends], "production_ids": jobs,
                               "engine": {"id": eng.id, "name": eng.name, "key": eng.key, "color": eng.color} if eng else None})


@router.get("/ideas")
def list_ideas(status: str | None = None, channel_id: int | None = None, engine_id: int | None = None, q: str | None = None,
               min_score: float | None = None, sort: str = "score", limit: int = 50, offset: int = 0,
               db: Session = Depends(get_db), _: User = Depends(viewer)):
    query = select(Idea)
    if status:
        query = query.where(Idea.status.in_(status.split(",")))
    if channel_id:
        query = query.where(Idea.channel_id == channel_id)
    if engine_id:
        query = query.where(Idea.engine_id == engine_id)
    if min_score is not None:
        query = query.where(Idea.total_score >= min_score)
    if q:
        query = query.where(or_(Idea.title.ilike(f"%{q}%"), Idea.description.ilike(f"%{q}%")))
    order = Idea.total_score.desc() if sort == "score" else Idea.created_at.desc()
    return page(db, query.order_by(order), limit=limit, offset=offset, mapper=lambda i: idea_view(db, i))


@router.post("/ideas", status_code=201)
def create_idea(body: IdeaIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    get_or_404(db, Channel, body.channel_id, "Canal")
    get_or_404(db, ContentEngine, body.engine_id, "Motor")
    data = body.model_dump(exclude={"trend_ids"})
    idea = Idea(**data, origin="manual", status="approved", dedupe_hash=ideas_svc.idea_hash(body.channel_id, body.title),
                generated_by=f"user:{user.id}")
    db.add(idea)
    db.flush()
    for tid in body.trend_ids:
        if db.get(Trend, tid):
            db.add(IdeaTrend(idea_id=idea.id, trend_id=tid))
    db.flush()
    ideas_svc.evaluate_ideas(db, [idea])
    audit(db, "idea.create", user_id=user.id, entity_type="idea", entity_id=idea.id)
    db.commit()
    return idea_view(db, idea)


@router.post("/ideas/generate")
def generate(body: IdeaGenerateIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    get_or_404(db, Channel, body.channel_id, "Canal")
    created = ideas_svc.generate_ideas(db, channel_id=body.channel_id, engine_id=body.engine_id, count=body.count,
                                       trend_ids=body.trend_ids or None, series_id=body.series_id)
    audit(db, "idea.generate", user_id=user.id, data={"count": len(created), "channel_id": body.channel_id})
    db.commit()
    return {"created": [idea_view(db, i) for i in created]}


@router.get("/ideas/{iid}")
def get_idea(iid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    return idea_view(db, get_or_404(db, Idea, iid, "Ideia"))


@router.patch("/ideas/{iid}")
def update_idea(iid: int, body: IdeaUpdate, db: Session = Depends(get_db), user: User = Depends(editor)):
    idea = get_or_404(db, Idea, iid, "Ideia")
    apply_updates(idea, body.model_dump(exclude_unset=True))
    audit(db, "idea.update", user_id=user.id, entity_type="idea", entity_id=iid)
    db.commit()
    return idea_view(db, idea)


@router.post("/ideas/{iid}/evaluate")
def reevaluate(iid: int, db: Session = Depends(get_db), _: User = Depends(editor)):
    idea = get_or_404(db, Idea, iid, "Ideia")
    ideas_svc.evaluate_ideas(db, [idea])
    db.commit()
    return idea_view(db, idea)


@router.post("/ideas/{iid}/produce")
def produce(iid: int, body: ProduceIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    idea = get_or_404(db, Idea, iid, "Ideia")
    if not idea.channel_id:
        raise HTTPException(422, "Ideia sem canal")
    jobs = []
    group = f"idea{idea.id}-{len(db.scalars(select(ProductionJob.id).where(ProductionJob.idea_id == idea.id)).all())}" if body.variants > 1 else None
    for k in range(body.variants):
        label = "ABCD"[k] if body.variants > 1 else None
        if k > 0:
            idea.status = "approved"  # permite as variantes
        cfg = {"variant": f"Versão {label}: varie o gancho e a estrutura" if label and k > 0 else None,
               "variant_group": group, "variant_label": label}
        job = create_production(db, channel_id=idea.channel_id, idea_id=idea.id, template_id=body.template_id,
                                priority=body.priority, user_id=user.id, config=cfg)
        jobs.append(job.id)
    return {"production_ids": jobs}


@router.delete("/ideas/{iid}", status_code=204)
def delete_idea(iid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    idea = get_or_404(db, Idea, iid, "Ideia")
    if idea.status == "in_production":
        raise HTTPException(409, "Ideia em produção")
    db.delete(idea)
    audit(db, "idea.delete", user_id=user.id, entity_type="idea", entity_id=iid)
    db.commit()
