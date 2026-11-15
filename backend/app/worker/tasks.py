"""Tarefas Celery. O `scheduler_tick` (a cada minuto) lê a tabela `workflows` (cron) e dispara automações."""
from __future__ import annotations

from datetime import UTC, datetime

from croniter import croniter
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.events import publish_event
from app.core.logging import get_logger
from app.models import AgentRun, Channel, Experiment, Workflow
from app.worker.celery_app import celery

log = get_logger(__name__)


def _agent_run(db, agent: str, fn, *, triggered_by: str = "schedule", channel_id: int | None = None) -> dict:
    """Executa um agente fora de produção registrando entrada/saída/erros em agent_runs (rastreabilidade)."""
    run = AgentRun(agent=agent, status="running", attempts=1, started_at=datetime.now(UTC), triggered_by=triggered_by,
                   channel_id=channel_id, input={})
    db.add(run)
    db.commit()
    publish_event("agent.started", {"agent": agent, "run_id": run.id})
    try:
        out = fn() or {}
        run.status, run.output = "succeeded", out if isinstance(out, dict) else {"result": out}
        return run.output
    except Exception as e:  # noqa: BLE001
        db.rollback()
        run = db.get(AgentRun, run.id)
        run.status, run.error = "failed", str(e)[:4000]
        log.exception("agente falhou", extra={"agent": agent})
        raise
    finally:
        run.finished_at = datetime.now(UTC)
        run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
        db.commit()
        publish_event("agent.finished", {"agent": agent, "run_id": run.id, "status": run.status})


@celery.task(name="app.worker.tasks.advance_production", bind=True, max_retries=0)
def advance_production(self, job_id: int) -> str:
    from app.pipeline.orchestrator import advance

    return advance(job_id)


@celery.task(name="app.worker.tasks.trend_research")
def trend_research(source_keys: list[str] | None = None, triggered_by: str = "schedule") -> dict:
    from app.services import trends

    with SessionLocal() as db:
        out = _agent_run(db, "trend_researcher", lambda: trends.research(db, source_keys), triggered_by=triggered_by)
        try:
            _agent_run(db, "trend_analyst", lambda: trends.analyze(db), triggered_by=triggered_by)
        except Exception:  # noqa: BLE001
            pass
        return out


@celery.task(name="app.worker.tasks.generate_ideas")
def generate_ideas(channel_id: int, engine_id: int | None = None, count: int = 8, triggered_by: str = "schedule") -> dict:
    from app.services.ideas import generate_ideas as gen

    with SessionLocal() as db:
        return _agent_run(db, "idea_generator",
                          lambda: {"created": [i.id for i in gen(db, channel_id=channel_id, engine_id=engine_id, count=count)]},
                          triggered_by=triggered_by, channel_id=channel_id)


@celery.task(name="app.worker.tasks.idea_generation_all")
def idea_generation_all() -> dict:
    with SessionLocal() as db:
        ids = db.scalars(select(Channel.id).where(Channel.is_active.is_(True), Channel.autonomy_mode != "manual")).all()
    out = {}
    for cid in ids:
        try:
            out[cid] = generate_ideas(cid)
        except Exception as e:  # noqa: BLE001
            out[cid] = {"error": str(e)[:200]}
    return out


@celery.task(name="app.worker.tasks.factory_tick")
def factory_tick(triggered_by: str = "schedule") -> dict:
    from app.services.factory import tick

    with SessionLocal() as db:
        return _agent_run(db, "factory_planner", lambda: tick(db), triggered_by=triggered_by)


@celery.task(name="app.worker.tasks.publish_due")
def publish_due() -> dict:
    from app.services.publishing import publish_due as pd

    with SessionLocal() as db:
        return {"processed": pd(db)}


@celery.task(name="app.worker.tasks.publish_one")
def publish_one(pub_id: int) -> str:
    from app.services.publishing import publish_publication

    with SessionLocal() as db:
        return publish_publication(db, pub_id, force=False).status


@celery.task(name="app.worker.tasks.collect_metrics")
def collect_metrics(triggered_by: str = "schedule") -> dict:
    from app.services.analytics import collect_metrics as cm

    with SessionLocal() as db:
        return _agent_run(db, "analytics_agent", lambda: cm(db), triggered_by=triggered_by)


@celery.task(name="app.worker.tasks.optimization")
def optimization(triggered_by: str = "schedule") -> dict:
    from app.services.analytics import evaluate_experiment, optimize_channel, update_strategy_arms

    def run() -> dict:
        out = {}
        for ch in db.scalars(select(Channel).where(Channel.is_active.is_(True))).all():
            arms = update_strategy_arms(db, ch.id)
            dec = optimize_channel(db, ch.id)
            out[ch.slug] = {"arms": arms, "decision": dec.rationale.get("decision") if dec else None}
        for exp in db.scalars(select(Experiment).where(Experiment.status == "running")).all():
            out[f"exp{exp.id}"] = evaluate_experiment(db, exp).get("conclusion")
        return out

    with SessionLocal() as db:
        return _agent_run(db, "optimization_agent", run, triggered_by=triggered_by)


@celery.task(name="app.worker.tasks.refresh_tokens")
def refresh_tokens() -> dict:
    from datetime import timedelta

    from app.models import SocialAccount
    from app.services.publishing import _account_creds

    n = 0
    with SessionLocal() as db:
        soon = datetime.now(UTC) + timedelta(hours=2)
        for acc in db.scalars(select(SocialAccount).where(SocialAccount.status == "connected", SocialAccount.token_expires_at < soon)).all():
            try:
                _account_creds(db, acc)
                n += 1
            except Exception:  # noqa: BLE001
                pass
    return {"refreshed": n}


@celery.task(name="app.worker.tasks.recover_stale")
def recover_stale() -> dict:
    from app.pipeline.orchestrator import recover_stale as rs

    with SessionLocal() as db:
        return {"recovered": rs(db)}


@celery.task(name="app.worker.tasks.provider_health")
def provider_health() -> dict:
    from app.services.providers_admin import refresh_status

    with SessionLocal() as db:
        return refresh_status(db, live=False)


WORKFLOW_TASKS = {
    "trend_research": trend_research, "idea_generation": idea_generation_all, "factory_tick": factory_tick,
    "publish_due": publish_due, "metrics_collection": collect_metrics, "optimization": optimization,
    "token_refresh": refresh_tokens, "recover_stale": recover_stale, "provider_health": provider_health,
}


@celery.task(name="app.worker.tasks.scheduler_tick")
def scheduler_tick() -> dict:
    now = datetime.now(UTC)
    fired = []
    with SessionLocal() as db:
        for wf in db.scalars(select(Workflow).where(Workflow.is_enabled.is_(True), Workflow.trigger == "cron")).all():
            if not wf.schedule or wf.key not in WORKFLOW_TASKS:
                continue
            base = wf.last_run_at or wf.created_at
            nxt = croniter(wf.schedule, base).get_next(datetime)
            if nxt <= now:
                wf.last_run_at, wf.run_count = now, wf.run_count + 1
                db.commit()
                try:
                    WORKFLOW_TASKS[wf.key].delay()
                    wf.last_status, wf.last_error = "dispatched", None
                except Exception as e:  # noqa: BLE001
                    wf.last_status, wf.last_error = "error", str(e)[:500]
                db.commit()
                fired.append(wf.key)
    return {"fired": fired}


def run_workflow_now(key: str) -> str | None:
    if key not in WORKFLOW_TASKS:
        raise KeyError(key)
    task = WORKFLOW_TASKS[key]
    kwargs = {"triggered_by": "user"} if "triggered_by" in task.run.__code__.co_varnames else {}
    return task.apply_async(kwargs=kwargs).id
