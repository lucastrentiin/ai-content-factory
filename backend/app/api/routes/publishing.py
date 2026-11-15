from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import editor, viewer
from app.api.utils import get_or_404, page, serialize
from app.core.db import get_db
from app.models import Asset, Channel, Publication, PublicationMetric, SocialAccount, User
from app.schemas import ManualMetricsIn, ManualPublishedIn, PublicationUpdate
from app.services import publishing as pubsvc
from app.services.analytics import engagement_score, record_manual_metrics
from app.services.assets import asset_public
from app.services.common import audit
from app.worker.dispatch import enqueue

router = APIRouter(tags=["publishing"])


def pub_view(db: Session, p: Publication) -> dict:
    last = db.scalar(select(PublicationMetric).where(PublicationMetric.publication_id == p.id).order_by(PublicationMetric.captured_at.desc()).limit(1))
    ch = db.get(Channel, p.channel_id)
    return serialize(p, extra={"channel": {"id": ch.id, "name": ch.name, "color": ch.color} if ch else None,
                               "cover": asset_public(db.get(Asset, p.cover_asset_id)) if p.cover_asset_id else None,
                               "video": asset_public(db.get(Asset, p.video_asset_id)) if p.video_asset_id else None,
                               "metrics": serialize(last) if last else None,
                               "score": engagement_score(last) if last else None})


@router.get("/publications")
def list_publications(status: str | None = None, channel_id: int | None = None, platform: str | None = None, limit: int = 50, offset: int = 0,
                      db: Session = Depends(get_db), _: User = Depends(viewer)):
    q = select(Publication)
    if status:
        q = q.where(Publication.status.in_(status.split(",")))
    if channel_id:
        q = q.where(Publication.channel_id == channel_id)
    if platform:
        q = q.where(Publication.platform_key == platform)
    return page(db, q.order_by(Publication.scheduled_at.desc().nullslast(), Publication.id.desc()), limit=limit, offset=offset,
                mapper=lambda p: pub_view(db, p))


@router.get("/publications/{pid}")
def get_publication(pid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    p = get_or_404(db, Publication, pid, "Publicação")
    metrics = db.scalars(select(PublicationMetric).where(PublicationMetric.publication_id == pid).order_by(PublicationMetric.captured_at)).all()
    return {**pub_view(db, p), "history": [serialize(m) for m in metrics]}


@router.patch("/publications/{pid}")
def update_publication(pid: int, body: PublicationUpdate, db: Session = Depends(get_db), user: User = Depends(editor)):
    p = get_or_404(db, Publication, pid, "Publicação")
    if p.status in ("published", "publishing"):
        raise HTTPException(409, "Publicação já enviada")
    data = body.model_dump(exclude_unset=True)
    if "social_account_id" in data and data["social_account_id"]:
        acc = get_or_404(db, SocialAccount, data["social_account_id"], "Conta")
        if acc.platform_key != p.platform_key or acc.channel_id != p.channel_id:
            raise HTTPException(422, "Conta incompatível com a publicação")
    if data.get("scheduled_at") and data["scheduled_at"] < datetime.now(UTC) - timedelta(minutes=1):
        raise HTTPException(422, "Horário no passado")
    for k, v in data.items():
        setattr(p, k, v)
    if "scheduled_at" in data and p.status in ("draft", "failed", "awaiting_manual") and data["scheduled_at"]:
        p.status, p.attempts, p.next_attempt_at = "scheduled", 0, None
    audit(db, "publication.update", user_id=user.id, entity_type="publication", entity_id=pid, data={"fields": list(data)})
    db.commit()
    return pub_view(db, p)


@router.post("/publications/{pid}/publish-now")
def publish_now(pid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    p = get_or_404(db, Publication, pid, "Publicação")
    if p.status in ("published", "publishing"):
        raise HTTPException(409, "Já publicada/em envio")
    p.scheduled_at = datetime.now(UTC)
    p.status, p.attempts, p.next_attempt_at = "scheduled", 0, None
    audit(db, "publication.publish_now", user_id=user.id, entity_type="publication", entity_id=pid)
    db.commit()
    enqueue("publish_one", pid)
    return pub_view(db, p)


@router.post("/publications/{pid}/cancel")
def cancel_publication(pid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    p = get_or_404(db, Publication, pid, "Publicação")
    if p.status == "published":
        raise HTTPException(409, "Já publicada — remova manualmente na plataforma")
    p.status = "cancelled"
    audit(db, "publication.cancel", user_id=user.id, entity_type="publication", entity_id=pid)
    db.commit()
    return pub_view(db, p)


@router.get("/publications/{pid}/export")
def export(pid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    p = get_or_404(db, Publication, pid, "Publicação")
    data = pubsvc.export_package(db, p)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="publicacao_{p.id}_{p.platform_key}.zip"'})


@router.post("/publications/{pid}/mark-published")
def mark_published(pid: int, body: ManualPublishedIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    p = get_or_404(db, Publication, pid, "Publicação")
    return pub_view(db, pubsvc.mark_manual_published(db, p, body.url, body.external_id, user.id))


@router.post("/publications/{pid}/metrics", status_code=201)
def manual_metrics(pid: int, body: ManualMetricsIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    p = get_or_404(db, Publication, pid, "Publicação")
    if p.status != "published":
        raise HTTPException(409, "Registre métricas apenas de publicações publicadas")
    m = record_manual_metrics(db, p, body.model_dump())
    return serialize(m)


@router.get("/calendar")
def calendar(start: datetime, end: datetime, channel_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(viewer)):
    if end <= start or end - start > timedelta(days=100):
        raise HTTPException(422, "Intervalo inválido (máx. 100 dias)")
    return pubsvc.calendar(db, start, end, channel_id)


@router.get("/channels/{cid}/next-slots")
def next_slots(cid: int, platform: str = "youtube", count: int = 5, db: Session = Depends(get_db), _: User = Depends(viewer)):
    ch = get_or_404(db, Channel, cid, "Canal")
    return [s.isoformat() for s in pubsvc.next_slots(db, ch, min(count, 20), platform)]
