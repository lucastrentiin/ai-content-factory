"""Biblioteca de assets: upload, listagem, download com suporte a Range (streaming de vídeo)."""
from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import COOKIE, editor, resolve_user, viewer
from app.api.utils import apply_updates, get_or_404, page, serialize
from app.core.db import get_db
from app.models import Asset, User
from app.schemas import AssetUpdate
from app.services.assets import asset_public, store_asset
from app.services.common import audit
from app.storage import get_storage

router = APIRouter(tags=["assets"])
MAX_UPLOAD = 500 * 1024 * 1024
ALLOWED = ("image/", "video/", "audio/", "font/", "application/x-font", "text/x-ssa")


@router.get("/assets")
def list_assets(kind: str | None = None, channel_id: int | None = None, production_job_id: int | None = None, q: str | None = None,
                reusable: bool | None = None, limit: int = 60, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(viewer)):
    query = select(Asset)
    if kind:
        query = query.where(Asset.kind.in_(kind.split(",")))
    if channel_id:
        query = query.where(Asset.channel_id == channel_id)
    if production_job_id:
        query = query.where(Asset.production_job_id == production_job_id)
    if reusable is not None:
        query = query.where(Asset.is_reusable.is_(reusable))
    if q:
        query = query.where(or_(Asset.name.ilike(f"%{q}%"), Asset.prompt.ilike(f"%{q}%")))
    return page(db, query.order_by(Asset.created_at.desc()), limit=limit, offset=offset,
                mapper=lambda a: serialize(a, extra={"url": asset_public(a)["url"]}))


@router.post("/assets", status_code=201)
async def upload_asset(file: UploadFile = File(...), kind: str = Form("image"), license: str = Form("user_owned"),
                       channel_id: int | None = Form(None), tags: str = Form(""), license_note: str = Form(""),
                       db: Session = Depends(get_db), user: User = Depends(editor)):
    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if not mime.startswith(ALLOWED):
        raise HTTPException(415, f"Tipo de arquivo não permitido: {mime}")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Arquivo maior que 500 MB")
    if kind not in ("image", "video", "audio", "music", "sfx", "font", "other"):
        raise HTTPException(422, "Tipo inválido")
    a = store_asset(db, kind=kind, name=file.filename or "arquivo", data=data, mime=mime, origin="uploaded", license=license,
                    license_note=license_note, channel_id=channel_id, is_reusable=True,
                    tags=[t.strip() for t in tags.split(",") if t.strip()])
    audit(db, "asset.upload", user_id=user.id, entity_type="asset", entity_id=a.id, data={"license": license})
    db.commit()
    return serialize(a, extra={"url": asset_public(a)["url"]})


@router.patch("/assets/{aid}")
def update_asset(aid: int, body: AssetUpdate, db: Session = Depends(get_db), _: User = Depends(editor)):
    a = apply_updates(get_or_404(db, Asset, aid, "Asset"), body.model_dump(exclude_unset=True))
    db.commit()
    return serialize(a, extra={"url": asset_public(a)["url"]})


@router.delete("/assets/{aid}", status_code=204)
def delete_asset(aid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    a = get_or_404(db, Asset, aid, "Asset")
    try:
        db.delete(a)
        db.flush()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(409, "Asset em uso") from e
    get_storage().delete(a.storage_key)
    audit(db, "asset.delete", user_id=user.id, entity_type="asset", entity_id=aid)
    db.commit()


@router.get("/assets/{aid}/file")
def asset_file(aid: int, request: Request, download: bool = False, db: Session = Depends(get_db)):
    # autenticação via cookie (tags <video>/<img>) ou Bearer
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get(COOKIE)
    if not resolve_user(db, token):
        raise HTTPException(401, "Não autenticado")
    a = get_or_404(db, Asset, aid, "Asset")
    st = get_storage()
    size = st.size(a.storage_key)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{a.name}"'
    rng = request.headers.get("range")
    if rng and rng.startswith("bytes="):
        s, _, e = rng[6:].partition("-")
        start = int(s) if s else max(0, size - int(e))
        end = int(e) if (e and s) else size - 1
        end = min(end, size - 1)
        if start >= size:
            raise HTTPException(416, "Faixa inválida")
        headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
        return StreamingResponse(st.iter_chunks(a.storage_key, start, end), status_code=206, media_type=a.mime, headers=headers)
    headers["Content-Length"] = str(size)
    return StreamingResponse(st.iter_chunks(a.storage_key), media_type=a.mime, headers=headers)
