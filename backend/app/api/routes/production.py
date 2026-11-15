"""Produções, cenas, renderizações, monitoramento da fábrica e execuções de agentes."""
from __future__ import annotations

import copy

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import editor, viewer
from app.api.utils import get_or_404, page, serialize
from app.core.db import get_db
from app.core.errors import ValidationFailed
from app.core.events import redis_client
from app.models import (
    AgentRun,
    ApiUsage,
    Asset,
    Channel,
    ContentEngine,
    ProductionJob,
    Publication,
    RenderJob,
    Scene,
    Script,
    ScriptVersion,
    User,
)
from app.pipeline import orchestrator as orch
from app.schemas import ProductionIn, RejectIn, RerunIn, SceneEditIn, SceneRerenderIn
from app.services.assets import asset_public
from app.services.scripts import add_version, normalize_script

router = APIRouter(tags=["production"])


def job_summary(db: Session, j: ProductionJob) -> dict:
    ch = db.get(Channel, j.channel_id)
    eng = db.get(ContentEngine, j.engine_id)
    return serialize(j, exclude={"config"}, extra={
        "channel": {"id": ch.id, "name": ch.name, "color": ch.color} if ch else None,
        "engine": {"id": eng.id, "name": eng.name, "key": eng.key, "color": eng.color} if eng else None,
        "video": asset_public(db.get(Asset, j.output_asset_id)) if j.output_asset_id else None,
        "thumbnail": asset_public(db.get(Asset, j.thumbnail_asset_id)) if j.thumbnail_asset_id else None,
        "review_reasons": (j.config or {}).get("review_reasons", []),
    })


@router.get("/productions")
def list_productions(status: str | None = None, channel_id: int | None = None, engine_id: int | None = None, q: str | None = None,
                     limit: int = 30, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(viewer)):
    query = select(ProductionJob)
    if status:
        query = query.where(ProductionJob.status.in_(status.split(",")))
    if channel_id:
        query = query.where(ProductionJob.channel_id == channel_id)
    if engine_id:
        query = query.where(ProductionJob.engine_id == engine_id)
    if q:
        query = query.where(ProductionJob.title.ilike(f"%{q}%"))
    return page(db, query.order_by(ProductionJob.created_at.desc()), limit=limit, offset=offset, mapper=lambda j: job_summary(db, j))


@router.post("/productions", status_code=201)
def create(body: ProductionIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    if body.manual_script:
        try:
            normalize_script(body.manual_script)
        except ValueError as e:
            raise ValidationFailed(f"Roteiro manual inválido: {e}") from e
    job = orch.create_production(db, user_id=user.id, **body.model_dump())
    return job_summary(db, job)


@router.get("/productions/{jid}")
def detail(jid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    j = get_or_404(db, ProductionJob, jid, "Produção")
    runs = db.scalars(select(AgentRun).where(AgentRun.production_job_id == jid).order_by(AgentRun.step_order)).all()
    scenes = db.scalars(select(Scene).where(Scene.production_job_id == jid).order_by(Scene.index)).all()
    renders = db.scalars(select(RenderJob).where(RenderJob.production_job_id == jid).order_by(RenderJob.id.desc()).limit(60)).all()
    pubs = db.scalars(select(Publication).where(Publication.production_job_id == jid)).all()
    usage = db.execute(select(ApiUsage.provider_key, ApiUsage.kind, func.count(), func.sum(func.coalesce(ApiUsage.actual_cost_usd, ApiUsage.est_cost_usd)))
                       .where(ApiUsage.production_job_id == jid).group_by(ApiUsage.provider_key, ApiUsage.kind)).all()
    script = db.get(Script, j.script_id) if j.script_id else None
    version = db.scalar(select(ScriptVersion).where(ScriptVersion.script_id == script.id, ScriptVersion.version == script.current_version)) if script else None

    def scene_view(s: Scene) -> dict:
        return serialize(s, extra={
            "clip": asset_public(db.get(Asset, s.clip_asset_id)) if s.clip_asset_id else None,
            "audio": asset_public(db.get(Asset, s.audio_asset_id)) if s.audio_asset_id else None,
            "image": asset_public(db.get(Asset, s.image_asset_id)) if s.image_asset_id else None})

    return {**job_summary(db, j), "config": {k: v for k, v in (j.config or {}).items() if k != "manual_script"},
            "steps": [serialize(r) for r in runs], "scenes": [scene_view(s) for s in scenes],
            "renders": [serialize(r) for r in renders], "publications": [serialize(p) for p in pubs],
            "costs": [{"provider": p, "kind": k, "calls": n, "cost_usd": round(c or 0, 5)} for p, k, n, c in usage],
            "script": serialize(script) if script else None, "script_version": serialize(version) if version else None,
            "pipeline": orch.STEP_NAMES}


@router.post("/productions/{jid}/continue")
def cont(jid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    return job_summary(db, orch.continue_manual(db, jid, user_id=user.id))


@router.post("/productions/{jid}/resume")
def resume(jid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    return job_summary(db, orch.resume(db, jid, user_id=user.id))


@router.post("/productions/{jid}/cancel")
def cancel(jid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    return job_summary(db, orch.cancel(db, jid, user_id=user.id))


@router.post("/productions/{jid}/approve")
def approve(jid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    return job_summary(db, orch.approve(db, jid, user_id=user.id))


@router.post("/productions/{jid}/reject")
def reject(jid: int, body: RejectIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    return job_summary(db, orch.reject(db, jid, reason=body.reason, user_id=user.id))


@router.post("/productions/{jid}/rerun")
def rerun(jid: int, body: RerunIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    return job_summary(db, orch.rerun_from(db, jid, body.step, user_id=user.id))


@router.post("/productions/{jid}/scenes/{index}/rerender")
def rerender(jid: int, index: int, body: SceneRerenderIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    return job_summary(db, orch.rerender_scene(db, jid, index, regenerate_visual=body.regenerate_visual,
                                               regenerate_audio=body.regenerate_audio, user_id=user.id))


@router.patch("/productions/{jid}/scenes/{index}")
def edit_scene(jid: int, index: int, body: SceneEditIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    """Edita uma cena: cria nova versão do roteiro e reprocessa a partir do planejamento (demais cenas ficam em cache)."""
    j = get_or_404(db, ProductionJob, jid, "Produção")
    if j.status == "running":
        raise HTTPException(409, "Produção em execução")
    script = get_or_404(db, Script, j.script_id, "Roteiro")
    v = db.scalar(select(ScriptVersion).where(ScriptVersion.script_id == script.id, ScriptVersion.version == script.current_version))
    content = copy.deepcopy(v.content)
    scene = next((s for s in content["scenes"] if s["index"] == index), None)
    if scene is None:
        raise HTTPException(404, "Cena não encontrada")
    for k, val in body.model_dump(exclude_unset=True).items():
        scene[k] = val
    try:
        content = normalize_script(content)
    except ValueError as e:
        raise ValidationFailed(f"Edição inválida: {e}") from e
    for c in content["characters"]:  # preserva vínculos já resolvidos
        prev = next((p for p in v.content["characters"] if p["name"] == c["name"]), None)
        if prev and prev.get("character_id"):
            c["character_id"] = prev["character_id"]
    for loc in content["locations"]:
        prev = next((p for p in v.content["locations"] if p["name"] == loc["name"]), None)
        if prev and prev.get("location_id"):
            loc["location_id"] = prev["location_id"]
    add_version(db, script, content, created_by=f"user:{user.id}", notes=f"Edição da cena {index}")
    db.commit()
    return job_summary(db, orch.rerun_from(db, jid, "character_designer", user_id=user.id))


@router.get("/render-jobs")
def render_jobs(status: str | None = None, limit: int = 50, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(viewer)):
    q = select(RenderJob)
    if status:
        q = q.where(RenderJob.status == status)
    return page(db, q.order_by(RenderJob.id.desc()), limit=limit, offset=offset)


@router.get("/agent-runs")
def agent_runs(status: str | None = None, agent: str | None = None, production_job_id: int | None = None, limit: int = 50, offset: int = 0,
               db: Session = Depends(get_db), _: User = Depends(viewer)):
    q = select(AgentRun)
    if status:
        q = q.where(AgentRun.status.in_(status.split(",")))
    if agent:
        q = q.where(AgentRun.agent == agent)
    if production_job_id:
        q = q.where(AgentRun.production_job_id == production_job_id)
    return page(db, q.order_by(AgentRun.updated_at.desc()), limit=limit, offset=offset)


AGENTS = [
    ("trend_researcher", "Pesquisador de Tendências"), ("trend_analyst", "Analista de Tendências"), ("idea_generator", "Gerador de Ideias"),
    ("factory_planner", "Planejador da Fábrica"), ("story_writer", "Roteirista"), ("script_editor", "Editor de Roteiro"),
    ("fact_checker", "Verificador de Fatos"), ("character_designer", "Designer de Personagens"), ("art_director", "Diretor de Arte"),
    ("scene_planner", "Planejador de Cenas"), ("voice_director", "Diretor de Voz"), ("audio_generator", "Gerador de Áudio"),
    ("visual_generator", "Gerador Visual"), ("video_editor", "Editor de Vídeo"), ("quality_controller", "Controle de Qualidade"),
    ("publisher", "Publicador"), ("analytics_agent", "Analista de Métricas"), ("optimization_agent", "Otimizador"),
]


@router.get("/monitor")
def monitor(db: Session = Depends(get_db), _: User = Depends(viewer)):
    agents = []
    for key, label in AGENTS:
        running = db.scalars(select(AgentRun).where(AgentRun.agent == key, AgentRun.status == "running").order_by(AgentRun.started_at.desc())).all()
        last = db.scalar(select(AgentRun).where(AgentRun.agent == key).order_by(AgentRun.updated_at.desc()).limit(1))
        stats = dict(db.execute(select(AgentRun.status, func.count()).where(AgentRun.agent == key).group_by(AgentRun.status)).all())
        agents.append({"key": key, "label": label, "running": [serialize(r, exclude={"events", "input"}) for r in running],
                       "last": serialize(last, exclude={"events", "input"}) if last else None, "stats": stats,
                       "pending": stats.get("pending", 0)})
    queues = {}
    workers: list = []
    try:
        r = redis_client()
        queues = {q: r.llen(q) for q in ("default", "render")}
    except Exception:  # noqa: BLE001
        queues = {"erro": "redis indisponível"}
    try:
        from app.worker.celery_app import celery

        pong = celery.control.inspect(timeout=1.0).ping() or {}
        workers = sorted(pong.keys())
    except Exception:  # noqa: BLE001
        workers = []
    active = db.scalars(select(ProductionJob).where(ProductionJob.status.in_(["queued", "running", "paused"])).order_by(ProductionJob.created_at)).all()
    failed = db.scalars(select(AgentRun).where(AgentRun.status == "failed").order_by(AgentRun.updated_at.desc()).limit(15)).all()
    return {"agents": agents, "queues": queues, "workers": workers, "active_productions": [job_summary(db, j) for j in active],
            "recent_failures": [serialize(f, exclude={"events", "input"}) for f in failed]}


@router.get("/review-queue")
def review_queue(db: Session = Depends(get_db), _: User = Depends(viewer)):
    rows = db.scalars(select(ProductionJob).where(or_(ProductionJob.status == "needs_review", ProductionJob.status == "awaiting_approval"))
                      .order_by(ProductionJob.updated_at.desc())).all()
    return [job_summary(db, j) for j in rows]
