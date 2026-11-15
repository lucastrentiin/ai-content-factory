"""Agendamento e publicação (API oficial quando autorizada; caso contrário, publicação assistida)."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_json, encrypt_json
from app.core.errors import Conflict, FactoryError, IntegrationNotAuthorized, NotFound
from app.core.events import publish_event, redis_client
from app.integrations.social import get_platform
from app.integrations.social.base import PublishRequest
from app.models import Asset, Channel, ProductionJob, Publication, SocialAccount
from app.services.assets import fetch_to, read_asset
from app.services.common import audit, notify, syslog
from app.storage import get_storage

MAX_ATTEMPTS = 5


def next_slots(db: Session, channel: Channel, count: int, platform_key: str, after: datetime | None = None) -> list[datetime]:
    """Próximos horários livres respeitando horários preferenciais e quantidade diária do canal."""
    tz = ZoneInfo(channel.timezone or "America/Sao_Paulo")
    now = (after or datetime.now(UTC)).astimezone(tz)
    hours = sorted(channel.preferred_hours or ["18:00"])
    per_day = max(1, channel.videos_per_day or 1)
    taken = {p.scheduled_at.astimezone(tz).replace(second=0, microsecond=0)
             for p in db.scalars(select(Publication).where(Publication.channel_id == channel.id, Publication.platform_key == platform_key,
                                                           Publication.status.in_(["scheduled", "published", "publishing", "processing"]),
                                                           Publication.scheduled_at.isnot(None), Publication.scheduled_at >= now - timedelta(days=1)))}
    out: list[datetime] = []
    day: date = now.date()
    for _ in range(120):
        per_day_taken = sum(1 for t in taken if t.date() == day)
        for h in hours:
            if per_day_taken >= per_day or len(out) >= count:
                break
            hh, mm = (int(x) for x in h.split(":"))
            slot = datetime.combine(day, time(hh, mm), tz)
            if slot <= now + timedelta(minutes=5) or slot in taken:
                continue
            out.append(slot)
            taken.add(slot)
            per_day_taken += 1
        if len(out) >= count:
            break
        day += timedelta(days=1)
    return [s.astimezone(UTC) for s in out]


def schedule_job_publications(db: Session, job: ProductionJob) -> list[Publication]:
    channel = db.get(Channel, job.channel_id)
    pubs = list(db.scalars(select(Publication).where(Publication.production_job_id == job.id, Publication.status == "draft")))
    for p in pubs:
        slot = next_slots(db, channel, 1, p.platform_key)[0]
        p.scheduled_at = slot
        p.status = "scheduled"
    db.flush()
    if pubs:
        publish_event("publications.scheduled", {"job_id": job.id, "count": len(pubs)})
    return pubs


def _account_creds(db: Session, acc: SocialAccount) -> dict:
    creds = decrypt_json(acc.credentials_encrypted)
    if acc.token_expires_at and acc.token_expires_at < datetime.now(UTC) + timedelta(minutes=10):
        plat = get_platform(acc.platform_key)
        try:
            res = plat.refresh(creds)
        except FactoryError as e:
            acc.status, acc.last_error = "expired", e.message
            db.commit()
            raise IntegrationNotAuthorized(f"Token expirado e não renovável: {e.message}") from e
        creds = res["creds"]
        acc.credentials_encrypted = encrypt_json(creds)
        acc.token_expires_at = plat.expires_at(res.get("expires_in"))
        db.commit()
    return creds


def publish_publication(db: Session, pub_id: int, *, force: bool = False) -> Publication:
    """Publica uma publicação agendada (idempotente, com lock e retentativas com backoff)."""
    lock = redis_client().lock(f"lock:publication:{pub_id}", timeout=3600, blocking=False)
    if not lock.acquire(blocking=False):
        raise Conflict("Publicação já em andamento")
    try:
        pub = db.get(Publication, pub_id)
        if not pub:
            raise NotFound("Publicação não encontrada")
        if pub.status in ("published", "cancelled"):
            return pub
        if pub.status == "processing" and pub.external_id:
            return check_processing(db, pub)
        job = db.get(ProductionJob, pub.production_job_id)
        if job.status not in ("completed",) and not force:
            raise Conflict("Produção ainda não aprovada")
        acc = db.get(SocialAccount, pub.social_account_id) if pub.social_account_id else None
        if pub.mode != "api" or not acc or acc.status != "connected":
            pub.status = "awaiting_manual"
            notify(db, f"Publicação assistida pendente ({pub.platform_key})", f"{pub.title} — baixe o pacote e publique manualmente.",
                   level="info", category="publish", link="/publications", dedupe_key=f"manual-pub:{pub.id}")
            db.commit()
            return pub
        pub.status = "publishing"
        pub.attempts += 1
        db.commit()
        plat = get_platform(pub.platform_key)
        work = Path(settings.work_dir) / f"pub_{pub.id}"
        try:
            creds = _account_creds(db, acc)
            video = fetch_to(db.get(Asset, pub.video_asset_id), work)
            cover_asset = db.get(Asset, pub.cover_asset_id) if pub.cover_asset_id else None
            cover = fetch_to(cover_asset, work) if cover_asset else None
            storage = get_storage()
            req = PublishRequest(video_path=video, cover_path=cover, title=pub.title, description=pub.description, hashtags=pub.hashtags,
                                 privacy=pub.privacy, public_video_url=storage.public_url(db.get(Asset, pub.video_asset_id).storage_key, 7200),
                                 public_cover_url=storage.public_url(cover_asset.storage_key, 7200) if cover_asset else None)
            res = plat.publish(creds, {**(acc.config or {}), "language": db.get(Channel, pub.channel_id).language}, req)
        except IntegrationNotAuthorized as e:
            pub.status, pub.mode, pub.last_error = "awaiting_manual", "assisted", e.message
            notify(db, f"Publicação automática indisponível ({pub.platform_key})", e.message, level="warning", category="publish", link="/publications")
            db.commit()
            return pub
        except Exception as e:  # noqa: BLE001
            msg = getattr(e, "message", str(e))
            retryable = getattr(e, "retryable", True)
            pub.last_error = msg[:2000]
            if retryable and pub.attempts < MAX_ATTEMPTS:
                pub.status = "scheduled"
                pub.next_attempt_at = datetime.now(UTC) + timedelta(minutes=5 * 2 ** (pub.attempts - 1))
            else:
                pub.status = "failed"
                notify(db, f"Falha ao publicar no {pub.platform_key}", msg[:400], level="error", category="publish", link="/publications")
            syslog(db, "ERROR", "publisher", f"Falha publicação #{pub.id}: {msg[:300]}", publication_id=pub.id)
            db.commit()
            return pub
        _apply_result(db, pub, res)
        audit(db, "publication.publish", entity_type="publication", entity_id=pub.id, data={"status": pub.status, "url": pub.url})
        db.commit()
        return pub
    finally:
        try:
            lock.release()
        except Exception:  # noqa: BLE001
            pass


def _apply_result(db: Session, pub: Publication, res) -> None:
    pub.platform_response = res.raw
    pub.external_id = res.external_id or pub.external_id
    if res.status == "published":
        pub.status, pub.url, pub.published_at, pub.last_error = "published", res.url, datetime.now(UTC), None
        notify(db, f"Publicado no {pub.platform_key}", pub.title, level="success", category="publish", link=pub.url or "/publications")
        publish_event("publication.published", {"id": pub.id, "url": pub.url})
    elif res.status == "processing":
        pub.status = "processing"
    else:
        pub.status, pub.last_error = "failed", res.error


def check_processing(db: Session, pub: Publication) -> Publication:
    acc = db.get(SocialAccount, pub.social_account_id)
    plat = get_platform(pub.platform_key)
    ref = (pub.platform_response or {}).get("publish_id") or (pub.platform_response or {}).get("container_id") or pub.external_id
    res = plat.check_status(_account_creds(db, acc), acc.config or {}, ref)
    _apply_result(db, pub, res)
    db.commit()
    return pub


def publish_due(db: Session) -> int:
    now = datetime.now(UTC)
    due = db.scalars(select(Publication.id).where(
        Publication.status.in_(["scheduled", "processing"]), Publication.scheduled_at <= now,
        (Publication.next_attempt_at.is_(None)) | (Publication.next_attempt_at <= now)).limit(20)).all()
    n = 0
    for pid in due:
        try:
            publish_publication(db, pid)
            n += 1
        except Conflict:
            continue
    return n


def export_package(db: Session, pub: Publication) -> bytes:
    """Pacote para publicação assistida: vídeo, capa e metadados."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        video = db.get(Asset, pub.video_asset_id)
        if video:
            z.writestr("video.mp4", read_asset(video))
        if pub.cover_asset_id:
            z.writestr("capa.jpg", read_asset(db.get(Asset, pub.cover_asset_id)))
        meta = {"plataforma": pub.platform_key, "titulo": pub.title, "descricao": pub.description, "hashtags": pub.hashtags,
                "agendado_para": pub.scheduled_at.isoformat() if pub.scheduled_at else None,
                "aviso": "Conteúdo gerado com auxílio de IA — marque como 'conteúdo gerado por IA' na plataforma quando aplicável."}
        z.writestr("metadados.json", json.dumps(meta, ensure_ascii=False, indent=2))
        z.writestr("legenda.txt", f"{pub.title}\n\n{pub.description}\n\n{' '.join(pub.hashtags)}")
    return buf.getvalue()


def mark_manual_published(db: Session, pub: Publication, url: str, external_id: str | None, user_id: int | None) -> Publication:
    pub.status, pub.url, pub.external_id = "published", url, external_id or pub.external_id
    pub.published_at = datetime.now(UTC)
    pub.mode = "assisted"
    audit(db, "publication.manual_published", user_id=user_id, entity_type="publication", entity_id=pub.id, data={"url": url})
    db.commit()
    return pub


def calendar(db: Session, start: datetime, end: datetime, channel_id: int | None = None) -> list[dict]:
    q = select(Publication).where(func.coalesce(Publication.scheduled_at, Publication.published_at) >= start,
                                  func.coalesce(Publication.scheduled_at, Publication.published_at) < end)
    if channel_id:
        q = q.where(Publication.channel_id == channel_id)
    return [{"id": p.id, "title": p.title, "platform": p.platform_key, "status": p.status, "channel_id": p.channel_id,
             "production_job_id": p.production_job_id, "scheduled_at": p.scheduled_at, "published_at": p.published_at, "url": p.url}
            for p in db.scalars(q.order_by(Publication.scheduled_at))]
