from __future__ import annotations

import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import editor, viewer
from app.api.utils import apply_updates, get_or_404, serialize
from app.core.config import settings
from app.core.crypto import encrypt_json
from app.core.db import get_db
from app.core.security import sign_state, verify_state
from app.integrations.social import PLATFORMS, get_platform
from app.models import (
    Channel,
    ChannelEngine,
    ContentCategory,
    ContentEngine,
    Platform,
    ProductionJob,
    SocialAccount,
    User,
)
from app.schemas import (
    ChannelBase,
    ChannelEngineIn,
    ChannelIn,
    EngineIn,
    EngineUpdate,
    SocialAccountIn,
    SocialAccountUpdate,
)
from app.services.common import audit

router = APIRouter(tags=["channels"])


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:100] or "canal"


def channel_view(db: Session, ch: Channel) -> dict:
    links = db.scalars(select(ChannelEngine).where(ChannelEngine.channel_id == ch.id)).all()
    accs = db.scalars(select(SocialAccount).where(SocialAccount.channel_id == ch.id)).all()
    counts = dict(db.execute(select(ProductionJob.status, func.count()).where(ProductionJob.channel_id == ch.id)
                             .group_by(ProductionJob.status)).all())
    return serialize(ch, extra={
        "engines": [serialize(link, extra={"engine": serialize(db.get(ContentEngine, link.engine_id))}) for link in links],
        "accounts": [account_view(a) for a in accs], "production_counts": counts})


def account_view(a: SocialAccount) -> dict:
    return serialize(a, extra={"has_credentials": bool(a.credentials_encrypted)})


@router.get("/platforms")
def list_platforms(db: Session = Depends(get_db), _: User = Depends(viewer)):
    out = []
    for p in db.scalars(select(Platform).order_by(Platform.id)):
        integ = PLATFORMS.get(p.key)
        ok, detail = integ.app_configured() if integ else (False, "Sem integração")
        out.append(serialize(p, extra={"app_configured": ok, "app_detail": detail, "docs": integ.docs if integ else None}))
    return out


@router.get("/channels")
def list_channels(db: Session = Depends(get_db), _: User = Depends(viewer)):
    return [channel_view(db, c) for c in db.scalars(select(Channel).order_by(Channel.name))]


@router.post("/channels", status_code=201)
def create_channel(body: ChannelIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    data = body.model_dump(exclude_none=True)
    engine_ids = data.pop("engine_ids", [])
    slug = base = slugify(body.name)
    i = 2
    while db.scalar(select(Channel.id).where(Channel.slug == slug)):
        slug, i = f"{base}-{i}", i + 1
    ch = Channel(slug=slug, **data)
    db.add(ch)
    db.flush()
    for eid in engine_ids or [e.id for e in db.scalars(select(ContentEngine).where(ContentEngine.is_active.is_(True)))]:
        if db.get(ContentEngine, eid):
            db.add(ChannelEngine(channel_id=ch.id, engine_id=eid))
    audit(db, "channel.create", user_id=user.id, entity_type="channel", entity_id=ch.id)
    db.commit()
    return channel_view(db, ch)


@router.get("/channels/{cid}")
def get_channel(cid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    return channel_view(db, get_or_404(db, Channel, cid, "Canal"))


@router.patch("/channels/{cid}")
def update_channel(cid: int, body: ChannelBase, db: Session = Depends(get_db), user: User = Depends(editor)):
    ch = get_or_404(db, Channel, cid, "Canal")
    data = body.model_dump(exclude_unset=True)
    if "settings" in data and data["settings"] is not None:
        data["settings"] = {**(ch.settings or {}), **data["settings"]}
    apply_updates(ch, data)
    audit(db, "channel.update", user_id=user.id, entity_type="channel", entity_id=ch.id, data={"fields": list(data)})
    db.commit()
    return channel_view(db, ch)


@router.delete("/channels/{cid}", status_code=204)
def delete_channel(cid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    ch = get_or_404(db, Channel, cid, "Canal")
    if db.scalar(select(func.count()).select_from(ProductionJob).where(ProductionJob.channel_id == cid, ProductionJob.status.in_(["queued", "running"]))):
        raise HTTPException(409, "Canal possui produções em andamento")
    audit(db, "channel.delete", user_id=user.id, entity_type="channel", entity_id=cid, data={"name": ch.name})
    db.delete(ch)
    db.commit()


@router.put("/channels/{cid}/engines")
def set_channel_engines(cid: int, body: list[ChannelEngineIn], db: Session = Depends(get_db), user: User = Depends(editor)):
    ch = get_or_404(db, Channel, cid, "Canal")
    existing = {link.engine_id: link for link in db.scalars(select(ChannelEngine).where(ChannelEngine.channel_id == cid))}
    seen = set()
    for item in body:
        if not db.get(ContentEngine, item.engine_id):
            raise HTTPException(422, f"Motor {item.engine_id} inexistente")
        link = existing.get(item.engine_id) or ChannelEngine(channel_id=cid, engine_id=item.engine_id, initial_weight=item.weight)
        link.is_enabled, link.weight, link.min_share, link.max_share = item.is_enabled, item.weight, item.min_share, item.max_share
        db.add(link)
        seen.add(item.engine_id)
    for eid, link in existing.items():
        if eid not in seen:
            db.delete(link)
    audit(db, "channel.engines", user_id=user.id, entity_type="channel", entity_id=cid)
    db.commit()
    return channel_view(db, ch)


# ---------------------------------------------------------------- contas sociais e OAuth
@router.post("/channels/{cid}/accounts", status_code=201)
def add_account(cid: int, body: SocialAccountIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    get_or_404(db, Channel, cid, "Canal")
    acc = SocialAccount(channel_id=cid, **body.model_dump())
    db.add(acc)
    audit(db, "account.create", user_id=user.id, entity_type="social_account", data={"platform": body.platform_key})
    db.commit()
    return account_view(acc)


@router.patch("/accounts/{aid}")
def update_account(aid: int, body: SocialAccountUpdate, db: Session = Depends(get_db), user: User = Depends(editor)):
    acc = get_or_404(db, SocialAccount, aid, "Conta")
    data = body.model_dump(exclude_unset=True)
    if data.get("config") is not None:
        data["config"] = {**(acc.config or {}), **data["config"]}
    apply_updates(acc, data)
    db.commit()
    return account_view(acc)


@router.delete("/accounts/{aid}", status_code=204)
def delete_account(aid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    acc = get_or_404(db, SocialAccount, aid, "Conta")
    audit(db, "account.delete", user_id=user.id, entity_type="social_account", entity_id=aid)
    db.delete(acc)
    db.commit()


def _redirect_uri(platform: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/oauth/{platform}/callback"


@router.get("/accounts/{aid}/connect")
def connect_account(aid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    acc = get_or_404(db, SocialAccount, aid, "Conta")
    plat = get_platform(acc.platform_key)
    ok, detail = plat.app_configured()
    if not ok:
        raise HTTPException(424, f"Aplicativo {plat.name} não configurado: {detail}")
    state = sign_state(f"{acc.id}:{user.id}")
    return {"auth_url": plat.auth_url(state, _redirect_uri(acc.platform_key)), "redirect_uri": _redirect_uri(acc.platform_key)}


@router.post("/accounts/{aid}/disconnect")
def disconnect_account(aid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    acc = get_or_404(db, SocialAccount, aid, "Conta")
    acc.credentials_encrypted, acc.status, acc.token_expires_at = None, "disconnected", None
    audit(db, "account.disconnect", user_id=user.id, entity_type="social_account", entity_id=aid)
    db.commit()
    return account_view(acc)


@router.get("/oauth/{platform}/callback", include_in_schema=False)
def oauth_callback(platform: str, state: str = "", code: str | None = None, error: str | None = Query(default=None),
                   db: Session = Depends(get_db)):
    front = settings.frontend_url.rstrip("/")
    data = verify_state(state)
    if not data:
        return RedirectResponse(f"{front}/channels?oauth=invalid_state")
    acc_id, user_id = (int(x) for x in data.split(":"))
    acc = db.get(SocialAccount, acc_id)
    if not acc or acc.platform_key != platform:
        return RedirectResponse(f"{front}/channels?oauth=invalid_account")
    if error or not code:
        acc.status, acc.last_error = "error", error or "Autorização negada"
        db.commit()
        return RedirectResponse(f"{front}/channels/{acc.channel_id}?oauth=denied")
    try:
        res = get_platform(platform).exchange_code(code, _redirect_uri(platform))
    except Exception as e:  # noqa: BLE001
        acc.status, acc.last_error = "error", getattr(e, "message", str(e))[:1000]
        db.commit()
        return RedirectResponse(f"{front}/channels/{acc.channel_id}?oauth=error")
    acc.credentials_encrypted = encrypt_json(res["creds"])
    acc.external_account_id = res["account"].get("id")
    acc.display_name = res["account"].get("name") or acc.display_name
    acc.token_expires_at = get_platform(platform).expires_at(res.get("expires_in"))
    acc.scopes = res.get("scopes", [])
    acc.status, acc.last_error, acc.publish_mode = "connected", None, "api"
    audit(db, "account.connected", user_id=user_id, entity_type="social_account", entity_id=acc.id)
    db.commit()
    return RedirectResponse(f"{front}/channels/{acc.channel_id}?oauth=connected")


# ---------------------------------------------------------------- motores e categorias
@router.get("/engines")
def list_engines(db: Session = Depends(get_db), _: User = Depends(viewer)):
    rows = db.scalars(select(ContentEngine).order_by(ContentEngine.is_system.desc(), ContentEngine.name)).all()
    usage = dict(db.execute(select(ProductionJob.engine_id, func.count()).group_by(ProductionJob.engine_id)).all())
    return [serialize(e, extra={"productions": usage.get(e.id, 0)}) for e in rows]


@router.post("/engines", status_code=201)
def create_engine(body: EngineIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    if db.scalar(select(ContentEngine.id).where(ContentEngine.key == body.key)):
        raise HTTPException(409, "Já existe um motor com essa chave")
    e = ContentEngine(**body.model_dump())
    db.add(e)
    audit(db, "engine.create", user_id=user.id, entity_type="engine", data={"key": body.key})
    db.commit()
    return serialize(e)


@router.patch("/engines/{eid}")
def update_engine(eid: int, body: EngineUpdate, db: Session = Depends(get_db), user: User = Depends(editor)):
    e = get_or_404(db, ContentEngine, eid, "Motor")
    data = body.model_dump(exclude_unset=True)
    if data.get("config") is not None:
        data["config"] = {**(e.config or {}), **data["config"]}
    apply_updates(e, data)
    audit(db, "engine.update", user_id=user.id, entity_type="engine", entity_id=eid)
    db.commit()
    return serialize(e)


@router.delete("/engines/{eid}", status_code=204)
def delete_engine(eid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    e = get_or_404(db, ContentEngine, eid, "Motor")
    if db.scalar(select(func.count()).select_from(ProductionJob).where(ProductionJob.engine_id == eid)):
        raise HTTPException(409, "Motor possui produções; desative-o em vez de excluir")
    audit(db, "engine.delete", user_id=user.id, entity_type="engine", entity_id=eid, data={"key": e.key})
    db.delete(e)
    db.commit()


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), _: User = Depends(viewer)):
    return [serialize(c) for c in db.scalars(select(ContentCategory).order_by(ContentCategory.name))]


@router.post("/categories", status_code=201)
def create_category(body: dict, db: Session = Depends(get_db), _: User = Depends(editor)):
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(422, "Nome obrigatório")
    c = ContentCategory(name=name, slug=slugify(name), engine_id=body.get("engine_id"))
    db.add(c)
    db.commit()
    return serialize(c)
