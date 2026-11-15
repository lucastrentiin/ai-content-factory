"""Orquestrador do pipeline de produção.

Cada produção percorre agentes com estado persistido (agent_runs): entradas, saídas, status, erros, tentativas e custo.
Execução protegida por lock distribuído (Redis) por produção → sem execuções concorrentes/duplicadas. Falhas
transitórias são re-tentadas com backoff exponencial; falhas de orçamento bloqueiam a produção; o controle de
qualidade pode solicitar a reexecução de etapas (autocorreção) ou enviar para revisão humana.
"""
from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.errors import BudgetExceeded, Conflict, FactoryError, NotFound, ValidationFailed
from app.core.events import publish_event, redis_client
from app.core.logging import get_logger
from app.models import (
    AgentRun,
    ApiUsage,
    Channel,
    ContentEngine,
    Episode,
    Idea,
    ProductionJob,
    Publication,
    Scene,
)
from app.models.enums import JobStatus, StepStatus
from app.pipeline.agents.audio import audio_generator, voice_director
from app.pipeline.agents.design import art_director, character_designer, scene_planner
from app.pipeline.agents.production import (
    RedoSteps,
    publisher,
    quality_controller,
    video_editor,
    visual_generator,
)
from app.pipeline.agents.writing import fact_checker, script_editor, story_writer
from app.pipeline.context import StepContext
from app.services.common import audit, notify, syslog

log = get_logger(__name__)

PIPELINE: list[tuple[str, Callable[[StepContext], dict], int]] = [
    # (agente, função, máx. tentativas)
    ("story_writer", story_writer, 3),
    ("script_editor", script_editor, 2),
    ("fact_checker", fact_checker, 2),
    ("character_designer", character_designer, 2),
    ("art_director", art_director, 2),
    ("scene_planner", scene_planner, 2),
    ("voice_director", voice_director, 2),
    ("audio_generator", audio_generator, 3),
    ("visual_generator", visual_generator, 2),
    ("video_editor", video_editor, 2),
    ("quality_controller", quality_controller, 2),
    ("publisher", publisher, 3),
]
STEP_NAMES = [s[0] for s in PIPELINE]
STEP_FUNCS = {s[0]: s[1] for s in PIPELINE}
STEP_WEIGHTS = {"story_writer": 0.08, "script_editor": 0.04, "fact_checker": 0.03, "character_designer": 0.05,
                "art_director": 0.07, "scene_planner": 0.03, "voice_director": 0.02, "audio_generator": 0.15,
                "visual_generator": 0.1, "video_editor": 0.33, "quality_controller": 0.06, "publisher": 0.04}
LOCK_TTL = 3 * 3600


def create_production(db: Session, *, channel_id: int, engine_id: int | None = None, idea_id: int | None = None,
                      title: str | None = None, series_id: int | None = None, episode_id: int | None = None,
                      manual_script: dict | None = None, template_id: int | None = None, priority: int = 5,
                      user_id: int | None = None, idempotency_key: str | None = None, config: dict | None = None,
                      visual_style: str | None = None, target_duration_s: int | None = None, autostart: bool = True) -> ProductionJob:
    if idempotency_key:
        existing = db.scalar(select(ProductionJob).where(ProductionJob.idempotency_key == idempotency_key))
        if existing:
            return existing
    channel = db.get(Channel, channel_id)
    if not channel:
        raise NotFound("Canal não encontrado")
    idea = db.get(Idea, idea_id) if idea_id else None
    if idea and idea.status == "in_production":
        active = db.scalar(select(ProductionJob).where(ProductionJob.idea_id == idea.id,
                                                       ProductionJob.status.in_(["queued", "running", "paused"])))
        if active:
            raise Conflict(f"Ideia já está em produção (produção #{active.id})")
    engine_id = engine_id or (idea.engine_id if idea else None)
    if not engine_id:
        raise ValidationFailed("Informe o motor de conteúdo")
    engine = db.get(ContentEngine, engine_id)
    if not engine or not engine.is_active:
        raise ValidationFailed("Motor inexistente ou desativado")
    if episode_id and not series_id:
        series_id = db.get(Episode, episode_id).series_id
    duration = target_duration_s or (idea.duration_s if idea else None) or channel.default_duration_s
    style = visual_style or (idea.visual_style if idea else None) or channel.visual_style
    job = ProductionJob(
        channel_id=channel.id, engine_id=engine.id, idea_id=idea.id if idea else None, series_id=series_id or (idea.series_id if idea else None),
        episode_id=episode_id, template_id=template_id, title=title or (idea.title if idea else "Nova produção"),
        status=JobStatus.queued, autonomy_mode=channel.autonomy_mode, priority=priority, visual_style=style,
        format=idea.format if idea else "narrated_story", target_duration_s=int(duration), idempotency_key=idempotency_key,
        created_by_id=user_id, est_cost_usd=float(idea.est_cost_usd) if idea else 0.0,
        config={**(config or {}), **({"manual_script": manual_script} if manual_script else {})},
        strategy={"engine": engine.key, "visual_style": style, "format": idea.format if idea else "narrated_story",
                  "duration_bucket": duration_bucket(int(duration)), "origin": idea.origin if idea else "manual"},
    )
    db.add(job)
    db.flush()
    for i, (name, _, max_att) in enumerate(PIPELINE):
        db.add(AgentRun(agent=name, production_job_id=job.id, step_order=i, status=StepStatus.pending, max_attempts=max_att,
                        channel_id=channel.id, input={}, triggered_by="user" if user_id else "system"))
    if idea:
        idea.status = "in_production"
    audit(db, "production.create", user_id=user_id, entity_type="production_job", entity_id=job.id)
    db.commit()
    publish_event("production.created", {"id": job.id, "title": job.title})
    if autostart:
        from app.worker.dispatch import enqueue

        enqueue("advance_production", job.id)
    return job


def duration_bucket(seconds: int) -> str:
    return "<=30s" if seconds <= 30 else ("31-45s" if seconds <= 45 else ("46-60s" if seconds <= 60 else ">60s"))


def _runs(db: Session, job_id: int) -> list[AgentRun]:
    return list(db.scalars(select(AgentRun).where(AgentRun.production_job_id == job_id).order_by(AgentRun.step_order)))


def _set_progress(job: ProductionJob, runs: list[AgentRun]) -> None:
    done = sum(STEP_WEIGHTS.get(r.agent, 0.05) for r in runs if r.status in (StepStatus.succeeded, StepStatus.skipped))
    job.progress = round(min(1.0, done / sum(STEP_WEIGHTS.values())), 3)


def advance(job_id: int) -> str:
    """Executa as etapas pendentes da produção até concluir, pausar, falhar ou agendar nova tentativa."""
    lock = redis_client().lock(f"lock:production:{job_id}", timeout=LOCK_TTL, blocking=False)
    if not lock.acquire(blocking=False):
        log.info("produção já em execução por outro worker", extra={"job_id": job_id})
        return "locked"
    try:
        return _advance_locked(job_id)
    finally:
        try:
            lock.release()
        except Exception:  # noqa: BLE001
            pass


def _advance_locked(job_id: int) -> str:
    db = SessionLocal()
    try:
        while True:
            job = db.get(ProductionJob, job_id)
            if job is None:
                return "missing"
            db.refresh(job)
            if job.status not in (JobStatus.queued, JobStatus.running):
                return job.status
            runs = _runs(db, job.id)
            run = next((r for r in runs if r.status not in (StepStatus.succeeded, StepStatus.skipped)), None)
            if run is None:
                return _finalize(db, job)
            if run.next_retry_at and run.next_retry_at > datetime.now(UTC):
                return "waiting_retry"
            if job.status == JobStatus.queued:
                job.status = JobStatus.running
                job.started_at = job.started_at or datetime.now(UTC)
            job.current_step = run.agent
            run.status = StepStatus.running
            run.attempts += 1
            run.started_at = datetime.now(UTC)
            run.error = run.error_code = None
            run.input = {"job_id": job.id, "attempt": run.attempts, "script_id": job.script_id}
            db.commit()
            publish_event("step.started", {"job_id": job.id, "agent": run.agent, "attempt": run.attempts})
            outcome = _execute(db, job, run)
            if outcome == "continue":
                db.refresh(job)
                if job.autonomy_mode == "manual" and job.status == JobStatus.running and _has_pending(db, job.id):
                    job.status = JobStatus.paused
                    db.commit()
                    publish_event("production.paused", {"id": job.id, "next": _next_pending(db, job.id)})
                    return "paused"
                continue
            return outcome
    finally:
        db.close()


def _has_pending(db: Session, job_id: int) -> bool:
    return _next_pending(db, job_id) is not None


def _next_pending(db: Session, job_id: int) -> str | None:
    r = db.scalar(select(AgentRun).where(AgentRun.production_job_id == job_id,
                                         AgentRun.status.notin_([StepStatus.succeeded, StepStatus.skipped]))
                  .order_by(AgentRun.step_order).limit(1))
    return r.agent if r else None


def _execute(db: Session, job: ProductionJob, run: AgentRun) -> str:
    t0 = time.time()
    try:
        ctx = StepContext.build(db, job, run)
        output = STEP_FUNCS[run.agent](ctx) or {}
        run.status = StepStatus.skipped if output.get("skipped") else StepStatus.succeeded
        run.output = output
        run.next_retry_at = None
        _close_run(db, run, t0)
        _set_progress(job, _runs(db, job.id))
        db.commit()
        publish_event("step.finished", {"job_id": job.id, "agent": run.agent, "status": run.status, "progress": job.progress})
        return "continue"
    except RedoSteps as redo:
        run.status = StepStatus.succeeded
        run.output = {"redo": redo.steps, "reason": redo.reason}
        _close_run(db, run, t0)
        for r in _runs(db, job.id):
            if r.agent in redo.steps:
                r.status, r.next_retry_at = StepStatus.pending, None
                r.attempts = 0 if r.agent != run.agent else r.attempts
        syslog(db, "INFO", "orchestrator", f"Produção #{job.id}: {redo.reason}", job_id=job.id)
        db.commit()
        publish_event("step.redo", {"job_id": job.id, "steps": redo.steps})
        return "continue"
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.get(ProductionJob, job.id)
        run = db.get(AgentRun, run.id)
        code = getattr(exc, "code", type(exc).__name__)
        msg = getattr(exc, "message", None) or str(exc)
        run.error = msg[:4000]
        run.error_code = str(code)[:40]
        run.events = [*(run.events or []), {"ts": datetime.now(UTC).isoformat(), "msg": "erro", "data": {"trace": traceback.format_exc()[-3000:]}}]
        _close_run(db, run, t0)
        if isinstance(exc, BudgetExceeded):
            run.status = StepStatus.failed
            job.status, job.error = JobStatus.blocked_budget, msg
            notify(db, f"Produção #{job.id} bloqueada por orçamento", msg, level="error", category="budget", link=f"/production/{job.id}")
            db.commit()
            publish_event("production.blocked", {"id": job.id, "reason": msg})
            return "blocked_budget"
        retryable = getattr(exc, "retryable", not isinstance(exc, (FactoryError, ValueError, KeyError, TypeError)))
        if retryable and run.attempts < run.max_attempts:
            delay = min(600, 15 * (2 ** (run.attempts - 1)))
            run.status = StepStatus.pending
            run.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
            db.commit()
            publish_event("step.retry", {"job_id": job.id, "agent": run.agent, "in_s": delay, "error": msg[:300]})
            from app.worker.dispatch import enqueue

            enqueue("advance_production", job.id, countdown=delay + 1)
            return "retry_scheduled"
        run.status = StepStatus.failed
        job.status, job.error = JobStatus.failed, f"{run.agent}: {msg}"[:4000]
        job.finished_at = datetime.now(UTC)
        notify(db, f"Produção #{job.id} falhou em {run.agent}", msg[:500], level="error", category="production", link=f"/production/{job.id}")
        syslog(db, "ERROR", "orchestrator", f"Produção #{job.id} falhou em {run.agent}: {msg[:500]}", job_id=job.id)
        db.commit()
        publish_event("production.failed", {"id": job.id, "agent": run.agent, "error": msg[:300]})
        return "failed"


def _close_run(db: Session, run: AgentRun, t0: float) -> None:
    run.finished_at = datetime.now(UTC)
    run.duration_ms = int((time.time() - t0) * 1000)
    rows = db.execute(select(ApiUsage.provider_key, func.coalesce(ApiUsage.actual_cost_usd, ApiUsage.est_cost_usd))
                      .where(ApiUsage.agent_run_id == run.id, ApiUsage.success.is_(True))).all()
    run.cost_usd = round(sum(r[1] or 0 for r in rows), 6)
    run.providers_used = sorted({r[0] for r in rows})


def _finalize(db: Session, job: ProductionJob) -> str:
    cfg = job.config or {}
    job.progress = 1.0
    job.current_step = None
    job.finished_at = datetime.now(UTC)
    channel = db.get(Channel, job.channel_id)
    if job.idea_id:
        db.get(Idea, job.idea_id).status = "produced"
    if job.episode_id:
        ep = db.get(Episode, job.episode_id)
        ep.status = "produced"
        ep.production_job_id = job.id
        _update_episode_continuity(db, job, ep)
    if cfg.get("force_review"):
        job.status = JobStatus.needs_review
        notify(db, f"Produção #{job.id} precisa de revisão", "; ".join(cfg.get("review_reasons", []))[:500],
               level="warning", category="qc", link=f"/production/{job.id}")
    elif job.autonomy_mode == "automatic" and not channel.require_approval:
        job.status = JobStatus.completed
        from app.services.publishing import schedule_job_publications

        schedule_job_publications(db, job)
    else:
        job.status = JobStatus.awaiting_approval
        notify(db, f"Vídeo pronto para aprovação: {job.title}", "", level="info", category="production", link=f"/production/{job.id}")
    db.commit()
    publish_event("production.finished", {"id": job.id, "status": job.status})
    return job.status


def _update_episode_continuity(db: Session, job: ProductionJob, ep: Episode) -> None:
    from app.models import Script, ScriptVersion

    sc = db.get(Script, job.script_id) if job.script_id else None
    if not sc:
        return
    v = db.scalar(select(ScriptVersion).where(ScriptVersion.script_id == sc.id, ScriptVersion.version == sc.current_version))
    c = v.content
    ep.title = v.title
    ep.summary = (v.synopsis + " " + v.full_story)[:1500]
    ep.hook_next = c.get("next_episode_hook", "")
    ep.continuity = {"characters": [ch["name"] for ch in c.get("characters", [])],
                     "locations": [loc["name"] for loc in c.get("locations", [])], "closing": v.closing}


# ------------------------------------------------------------------------------------------- comandos do usuário
def _get(db: Session, job_id: int) -> ProductionJob:
    job = db.get(ProductionJob, job_id)
    if not job:
        raise NotFound("Produção não encontrada")
    return job


def rerun_from(db: Session, job_id: int, agent: str, *, user_id: int | None = None, start: bool = True) -> ProductionJob:
    """Reprocessa a partir de uma etapa (ela e as seguintes voltam a pendente). Assets em cache são reaproveitados."""
    if agent not in STEP_NAMES:
        raise ValidationFailed("Etapa inválida")
    job = _get(db, job_id)
    if job.status == JobStatus.running:
        raise Conflict("Produção em execução; aguarde ou cancele")
    idx = STEP_NAMES.index(agent)
    for r in _runs(db, job.id):
        if r.step_order >= idx:
            r.status, r.attempts, r.next_retry_at, r.error = StepStatus.pending, 0, None, None
    cfg = dict(job.config or {})
    cfg.pop("qc_fix_attempts", None)
    if idx <= STEP_NAMES.index("quality_controller"):
        cfg.pop("force_review", None)
        cfg.pop("review_reasons", None)
    job.config = cfg
    job.status, job.error, job.finished_at = JobStatus.queued, None, None
    _set_progress(job, _runs(db, job.id))
    audit(db, "production.rerun", user_id=user_id, entity_type="production_job", entity_id=job.id, data={"from": agent})
    db.commit()
    if start:
        from app.worker.dispatch import enqueue

        enqueue("advance_production", job.id)
    return job


def rerender_scene(db: Session, job_id: int, scene_index: int, *, regenerate_visual: bool = False,
                   regenerate_audio: bool = False, user_id: int | None = None) -> ProductionJob:
    job = _get(db, job_id)
    sc = db.scalar(select(Scene).where(Scene.production_job_id == job.id, Scene.index == scene_index))
    if not sc:
        raise NotFound("Cena não encontrada")
    sc.needs_rerender = True
    if regenerate_visual:
        sc.image_asset_id = sc.video_asset_id = None
    start = "audio_generator" if regenerate_audio else ("visual_generator" if regenerate_visual else "video_editor")
    if regenerate_audio:
        from app.models import Asset

        for line in sc.audio_timeline or []:  # remove cache das falas desta cena
            a = db.get(Asset, line.get("asset_id"))
            if a:
                a.meta = {**(a.meta or {}), "line_hash": None}
    return rerun_from(db, job.id, start, user_id=user_id)


def continue_manual(db: Session, job_id: int, *, user_id: int | None = None) -> ProductionJob:
    job = _get(db, job_id)
    if job.status != JobStatus.paused:
        raise Conflict("A produção não está pausada")
    job.status = JobStatus.queued
    audit(db, "production.continue", user_id=user_id, entity_type="production_job", entity_id=job.id)
    db.commit()
    from app.worker.dispatch import enqueue

    enqueue("advance_production", job.id)
    return job


def resume(db: Session, job_id: int, *, user_id: int | None = None) -> ProductionJob:
    """Retoma produção falha/bloqueada a partir da etapa que falhou."""
    job = _get(db, job_id)
    if job.status not in (JobStatus.failed, JobStatus.blocked_budget, JobStatus.paused):
        raise Conflict("Somente produções falhas, bloqueadas ou pausadas podem ser retomadas")
    agent = _next_pending(db, job.id)
    if not agent:
        raise Conflict("Nada a retomar")
    return rerun_from(db, job.id, agent, user_id=user_id)


def cancel(db: Session, job_id: int, *, user_id: int | None = None) -> ProductionJob:
    job = _get(db, job_id)
    if job.status in (JobStatus.completed, JobStatus.cancelled):
        raise Conflict("Produção já finalizada")
    job.status = JobStatus.cancelled
    job.finished_at = datetime.now(UTC)
    for r in _runs(db, job.id):
        if r.status in (StepStatus.pending, StepStatus.waiting):
            r.status = StepStatus.cancelled
    for p in db.scalars(select(Publication).where(Publication.production_job_id == job.id, Publication.status.in_(["draft", "scheduled"]))):
        p.status = "cancelled"
    if job.idea_id:
        idea = db.get(Idea, job.idea_id)
        if idea and idea.status == "in_production":
            idea.status = "approved"
    audit(db, "production.cancel", user_id=user_id, entity_type="production_job", entity_id=job.id)
    db.commit()
    publish_event("production.cancelled", {"id": job.id})
    return job


def approve(db: Session, job_id: int, *, user_id: int | None = None, schedule: bool = True) -> ProductionJob:
    job = _get(db, job_id)
    if job.status not in (JobStatus.awaiting_approval, JobStatus.needs_review):
        raise Conflict("Produção não está aguardando aprovação")
    if not job.output_asset_id:
        raise Conflict("Produção sem vídeo final")
    job.status = JobStatus.completed
    job.approved_by_id = user_id
    if schedule:
        from app.services.publishing import schedule_job_publications

        schedule_job_publications(db, job)
    audit(db, "production.approve", user_id=user_id, entity_type="production_job", entity_id=job.id)
    db.commit()
    publish_event("production.approved", {"id": job.id})
    return job


def reject(db: Session, job_id: int, *, reason: str = "", user_id: int | None = None) -> ProductionJob:
    job = _get(db, job_id)
    if job.status not in (JobStatus.awaiting_approval, JobStatus.needs_review):
        raise Conflict("Produção não está aguardando aprovação")
    job.status = JobStatus.cancelled
    job.error = f"Rejeitado: {reason}"[:1000]
    for p in db.scalars(select(Publication).where(Publication.production_job_id == job.id, Publication.status == "draft")):
        p.status = "cancelled"
    audit(db, "production.reject", user_id=user_id, entity_type="production_job", entity_id=job.id, data={"reason": reason})
    db.commit()
    return job


def recover_stale(db: Session, older_than_min: int = 90) -> int:
    """Recupera produções 'running' órfãs (ex.: worker reiniciado) re-enfileirando a etapa."""
    limit = datetime.now(UTC) - timedelta(minutes=older_than_min)
    n = 0
    from app.worker.dispatch import enqueue

    for run in db.scalars(select(AgentRun).where(AgentRun.status == StepStatus.running, AgentRun.started_at < limit,
                                                 AgentRun.production_job_id.isnot(None))):
        if redis_client().get(f"lock:production:{run.production_job_id}"):
            continue
        run.status = StepStatus.pending
        job = db.get(ProductionJob, run.production_job_id)
        if job and job.status == JobStatus.running:
            job.status = JobStatus.queued
            n += 1
            db.commit()
            enqueue("advance_production", job.id)
    db.commit()
    # retentativas cujo horário já passou (também cobre o modo síncrono)
    due = db.scalars(select(AgentRun.production_job_id).where(AgentRun.status == StepStatus.pending,
                                                               AgentRun.next_retry_at.isnot(None),
                                                               AgentRun.next_retry_at <= datetime.now(UTC))).all()
    for jid in set(due):
        enqueue("advance_production", jid)
    return n
