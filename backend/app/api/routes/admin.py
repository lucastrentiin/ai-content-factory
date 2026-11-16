"""Administração: dashboard, usuários, tokens de API, provedores, automações, notificações, configurações, logs, auditoria."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import admin, current_user, editor, viewer
from app.api.utils import apply_updates, get_or_404, page, serialize
from app.core.db import get_db
from app.core.security import generate_api_token, hash_password
from app.models import (
    AgentRun,
    ApiToken,
    AuditLog,
    Channel,
    ModelProvider,
    Notification,
    ProductionJob,
    ProviderModel,
    Publication,
    SystemLog,
    User,
    Workflow,
)
from app.schemas import (
    ApiTokenIn,
    ProviderCredentialsIn,
    ProviderModelIn,
    ProviderUpdate,
    UserIn,
    UserUpdate,
    WorkflowUpdate,
)
from app.services import analytics as an
from app.services.common import DEFAULT_SETTINGS, audit, get_setting, set_setting
from app.services.costs import cost_summary
from app.services.providers_admin import provider_view, refresh_status, set_credentials, test_provider

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(viewer)):
    from app.api.routes.production import job_summary

    ov = an.overview(db, 30)
    costs = cost_summary(db, 30)
    recent_jobs = db.scalars(select(ProductionJob).order_by(ProductionJob.updated_at.desc()).limit(8)).all()
    upcoming = db.scalars(select(Publication).where(Publication.status == "scheduled").order_by(Publication.scheduled_at).limit(6)).all()
    activity = db.scalars(select(AgentRun).where(AgentRun.status.in_(["succeeded", "failed", "running"]))
                          .order_by(AgentRun.updated_at.desc()).limit(14)).all()
    alerts = db.scalars(select(Notification).where(Notification.is_read.is_(False), Notification.level.in_(["warning", "error"]))
                        .order_by(Notification.created_at.desc()).limit(6)).all()
    simulated = [p.name for p in db.scalars(select(ModelProvider).where(ModelProvider.is_simulated.is_(True), ModelProvider.is_enabled.is_(True)))]
    real_llm = [p for p in db.scalars(select(ModelProvider).where(ModelProvider.kind == "llm", ModelProvider.is_simulated.is_(False),
                                                                    ModelProvider.is_enabled.is_(True)))
                if provider_view(db, p)["status"] in ("configured", "manual")]
    manual = db.scalar(select(ModelProvider).where(ModelProvider.adapter == "manual_paste"))
    from app.models import ManualRequest

    pending_manual = db.scalars(select(ManualRequest).where(ManualRequest.status == "pending").order_by(ManualRequest.created_at)).all()
    return {"overview": ov, "costs": {k: costs[k] for k in ("today_usd", "month_usd", "total_usd", "avg_cost_per_video_usd", "by_day")},
            "recent_productions": [job_summary(db, j) for j in recent_jobs], "upcoming": [serialize(p) for p in upcoming],
            "activity": [serialize(a, exclude={"events", "input", "output"}) for a in activity], "alerts": [serialize(n) for n in alerts],
            "factory": get_setting(db, "automation"), "simulated_providers_enabled": simulated, "has_real_llm": bool(real_llm),
            "manual_mode": bool(manual and manual.is_enabled),
            "manual_pending": [serialize(r, exclude={"prompt", "response"}) for r in pending_manual],
            "channels": db.scalar(select(func.count()).select_from(Channel)) or 0}


# ---------------------------------------------------------------- usuários e tokens
@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(admin)):
    return [serialize(u) for u in db.scalars(select(User).order_by(User.id))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), me: User = Depends(admin)):
    if db.scalar(select(User.id).where(User.email == body.email.lower())):
        raise HTTPException(409, "E-mail já cadastrado")
    u = User(email=body.email.lower(), name=body.name, role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    audit(db, "user.create", user_id=me.id, entity_type="user", data={"email": u.email, "role": u.role})
    db.commit()
    return serialize(u)


@router.patch("/users/{uid}")
def update_user(uid: int, body: UserUpdate, db: Session = Depends(get_db), me: User = Depends(admin)):
    u = get_or_404(db, User, uid, "Usuário")
    data = body.model_dump(exclude_unset=True)
    if uid == me.id and (data.get("role") not in (None, "admin") or data.get("is_active") is False):
        raise HTTPException(422, "Você não pode remover seu próprio acesso de administrador")
    if data.get("password"):
        u.password_hash = hash_password(data.pop("password"))
    apply_updates(u, data)
    audit(db, "user.update", user_id=me.id, entity_type="user", entity_id=uid, data={"fields": list(data)})
    db.commit()
    return serialize(u)


@router.get("/api-tokens")
def list_tokens(db: Session = Depends(get_db), me: User = Depends(current_user)):
    return [serialize(t) for t in db.scalars(select(ApiToken).where(ApiToken.user_id == me.id).order_by(ApiToken.id.desc()))]


@router.post("/api-tokens", status_code=201)
def create_token(body: ApiTokenIn, db: Session = Depends(get_db), me: User = Depends(editor)):
    raw, h = generate_api_token()
    t = ApiToken(user_id=me.id, name=body.name, token_hash=h, prefix=raw[:10])
    db.add(t)
    audit(db, "api_token.create", user_id=me.id, data={"name": body.name})
    db.commit()
    return {**serialize(t), "token": raw, "warning": "Copie agora: o token não será exibido novamente."}


@router.delete("/api-tokens/{tid}", status_code=204)
def revoke_token(tid: int, db: Session = Depends(get_db), me: User = Depends(current_user)):
    t = get_or_404(db, ApiToken, tid, "Token")
    if t.user_id != me.id and me.role != "admin":
        raise HTTPException(403, "Sem permissão")
    t.revoked = True
    audit(db, "api_token.revoke", user_id=me.id, entity_type="api_token", entity_id=tid)
    db.commit()


# ---------------------------------------------------------------- provedores
@router.get("/providers")
def list_providers(db: Session = Depends(get_db), _: User = Depends(viewer)):
    return [provider_view(db, p) for p in db.scalars(select(ModelProvider).order_by(ModelProvider.kind, ModelProvider.priority))]


@router.patch("/providers/{pid}")
def update_provider(pid: int, body: ProviderUpdate, db: Session = Depends(get_db), me: User = Depends(admin)):
    p = get_or_404(db, ModelProvider, pid, "Provedor")
    data = body.model_dump(exclude_unset=True)
    if data.get("config") is not None:
        data["config"] = {**(p.config or {}), **data["config"]}
    apply_updates(p, data)
    audit(db, "provider.update", user_id=me.id, entity_type="provider", entity_id=pid, data={"fields": list(data)})
    db.commit()
    return provider_view(db, p)


@router.put("/providers/{pid}/credentials")
def provider_credentials(pid: int, body: ProviderCredentialsIn, db: Session = Depends(get_db), me: User = Depends(admin)):
    p = get_or_404(db, ModelProvider, pid, "Provedor")
    set_credentials(db, p, body.credentials)
    audit(db, "provider.credentials", user_id=me.id, entity_type="provider", entity_id=pid, data={"keys": list(body.credentials)})
    db.commit()
    return provider_view(db, p)


@router.post("/providers/{pid}/test")
def provider_test(pid: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    return test_provider(db, get_or_404(db, ModelProvider, pid, "Provedor"))


@router.post("/providers/refresh")
def providers_refresh(db: Session = Depends(get_db), _: User = Depends(admin)):
    return refresh_status(db)


@router.post("/providers/{pid}/models", status_code=201)
def add_model(pid: int, body: ProviderModelIn, db: Session = Depends(get_db), _: User = Depends(admin)):
    p = get_or_404(db, ModelProvider, pid, "Provedor")
    if body.is_default:
        db.execute(update(ProviderModel).where(ProviderModel.provider_id == pid).values(is_default=False))
    m = db.scalar(select(ProviderModel).where(ProviderModel.provider_id == pid, ProviderModel.model_key == body.model_key))
    m = m or ProviderModel(provider_id=pid, kind=p.kind, model_key=body.model_key, display_name=body.display_name)
    apply_updates(m, body.model_dump())
    db.add(m)
    db.commit()
    return provider_view(db, p)


@router.patch("/provider-models/{mid}")
def update_model(mid: int, body: ProviderModelIn, db: Session = Depends(get_db), _: User = Depends(admin)):
    m = get_or_404(db, ProviderModel, mid, "Modelo")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default"):
        db.execute(update(ProviderModel).where(ProviderModel.provider_id == m.provider_id, ProviderModel.id != mid).values(is_default=False))
    apply_updates(m, data)
    db.commit()
    return provider_view(db, db.get(ModelProvider, m.provider_id))


@router.delete("/provider-models/{mid}", status_code=204)
def delete_model(mid: int, db: Session = Depends(get_db), _: User = Depends(admin)):
    db.delete(get_or_404(db, ProviderModel, mid, "Modelo"))
    db.commit()


# ---------------------------------------------------------------- automações
@router.get("/workflows")
def list_workflows(db: Session = Depends(get_db), _: User = Depends(viewer)):
    from croniter import croniter

    out = []
    for w in db.scalars(select(Workflow).order_by(Workflow.id)):
        nxt = croniter(w.schedule, w.last_run_at or w.created_at).get_next(datetime) if w.schedule else None
        out.append(serialize(w, extra={"next_run_at": nxt.isoformat() if nxt else None}))
    return out


@router.patch("/workflows/{wid}")
def update_workflow(wid: int, body: WorkflowUpdate, db: Session = Depends(get_db), me: User = Depends(admin)):
    w = apply_updates(get_or_404(db, Workflow, wid, "Automação"), body.model_dump(exclude_unset=True))
    audit(db, "workflow.update", user_id=me.id, entity_type="workflow", entity_id=wid)
    db.commit()
    return serialize(w)


@router.post("/workflows/{wid}/run")
def run_workflow(wid: int, db: Session = Depends(get_db), me: User = Depends(editor)):
    from app.worker.tasks import run_workflow_now

    w = get_or_404(db, Workflow, wid, "Automação")
    task_id = run_workflow_now(w.key)
    w.last_run_at, w.last_status, w.run_count = datetime.now(UTC), "dispatched", w.run_count + 1
    audit(db, "workflow.run", user_id=me.id, entity_type="workflow", entity_id=wid)
    db.commit()
    return {"task_id": task_id}


# ---------------------------------------------------------------- notificações
@router.get("/notifications")
def notifications(unread: bool = False, limit: int = 30, offset: int = 0, db: Session = Depends(get_db), me: User = Depends(viewer)):
    q = select(Notification).where((Notification.user_id.is_(None)) | (Notification.user_id == me.id))
    if unread:
        q = q.where(Notification.is_read.is_(False))
    data = page(db, q.order_by(Notification.created_at.desc()), limit=limit, offset=offset)
    data["unread"] = db.scalar(select(func.count()).select_from(Notification).where(Notification.is_read.is_(False),
                                                                                     (Notification.user_id.is_(None)) | (Notification.user_id == me.id)))
    return data


@router.post("/notifications/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    n = get_or_404(db, Notification, nid, "Notificação")
    n.is_read = True
    db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def read_all(db: Session = Depends(get_db), me: User = Depends(viewer)):
    db.execute(update(Notification).where((Notification.user_id.is_(None)) | (Notification.user_id == me.id)).values(is_read=True))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- configurações, logs, auditoria
@router.get("/settings")
def all_settings(db: Session = Depends(get_db), _: User = Depends(viewer)):
    return {k: get_setting(db, k) for k in DEFAULT_SETTINGS}


@router.put("/settings/{key}")
def put_setting(key: str, body: dict, db: Session = Depends(get_db), me: User = Depends(admin)):
    if key not in DEFAULT_SETTINGS:
        raise HTTPException(404, "Configuração desconhecida")
    unknown = set(body) - set(DEFAULT_SETTINGS[key])
    if unknown:
        raise HTTPException(422, f"Campos desconhecidos: {sorted(unknown)}")
    for k, v in body.items():
        if type(DEFAULT_SETTINGS[key][k]) is not type(v) and not (isinstance(v, (int, float)) and isinstance(DEFAULT_SETTINGS[key][k], (int, float))):
            raise HTTPException(422, f"Tipo inválido para {k}")
    val = set_setting(db, key, body)
    audit(db, "settings.update", user_id=me.id, data={"key": key, "value": body})
    db.commit()
    return val


@router.get("/system/logs")
def system_logs(level: str | None = None, source: str | None = None, limit: int = 100, offset: int = 0,
                db: Session = Depends(get_db), _: User = Depends(admin)):
    q = select(SystemLog)
    if level:
        q = q.where(SystemLog.level == level.upper())
    if source:
        q = q.where(SystemLog.source == source)
    return page(db, q.order_by(SystemLog.created_at.desc()), limit=limit, offset=offset)


@router.get("/audit-logs")
def audit_logs(action: str | None = None, limit: int = 100, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(admin)):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action.ilike(f"{action}%"))
    users = {u.id: u.email for u in db.scalars(select(User))}
    return page(db, q.order_by(AuditLog.created_at.desc()), limit=limit, offset=offset,
                mapper=lambda a: serialize(a, extra={"user_email": users.get(a.user_id)}))


@router.post("/system/cleanup")
def cleanup(days: int = 30, db: Session = Depends(get_db), me: User = Depends(admin)):
    """Remove diretórios de trabalho temporários e logs de sistema antigos."""
    import shutil

    from app.core.config import settings

    removed = 0
    for p in settings.work_dir.glob("*"):
        if p.is_dir() and datetime.fromtimestamp(p.stat().st_mtime, UTC) < datetime.now(UTC) - timedelta(days=1):
            shutil.rmtree(p, ignore_errors=True)
            removed += 1
    n = db.query(SystemLog).filter(SystemLog.created_at < datetime.now(UTC) - timedelta(days=days)).delete()
    audit(db, "system.cleanup", user_id=me.id, data={"workdirs": removed, "logs": n})
    db.commit()
    return {"work_dirs_removed": removed, "logs_removed": n}
