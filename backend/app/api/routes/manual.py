"""Pedidos "copiar e colar": o usuário copia o prompt, cola no Claude (assinatura) e envia a resposta aqui."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import editor, viewer
from app.api.utils import get_or_404, serialize
from app.core.db import get_db
from app.core.errors import AwaitingManualInput, ProviderError
from app.models import ManualRequest, ModelProvider, ProductionJob, User
from app.providers import manual
from app.providers.router import parse_json
from app.schemas import In
from app.services.common import audit
from app.worker.dispatch import enqueue

router = APIRouter(tags=["manual"])


class AnswerIn(In):
    response: str = Field(min_length=2, max_length=400_000)


def view(db: Session, r: ManualRequest) -> dict:
    job = db.get(ProductionJob, r.production_job_id) if r.production_job_id else None
    return serialize(r, extra={"production_title": job.title if job else None})


@router.get("/manual-requests")
def list_requests(status: str = "pending", production_job_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(viewer)):
    q = select(ManualRequest).where(ManualRequest.status.in_(status.split(",")))
    if production_job_id:
        q = q.where(ManualRequest.production_job_id == production_job_id)
    return [view(db, r) for r in db.scalars(q.order_by(ManualRequest.created_at))]


@router.get("/manual-requests/{rid}")
def get_request(rid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    return view(db, get_or_404(db, ManualRequest, rid, "Pedido"))


@router.post("/manual-requests/{rid}/answer")
def answer(rid: int, body: AnswerIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    r = get_or_404(db, ManualRequest, rid, "Pedido")
    if r.status not in ("pending", "answered"):
        raise HTTPException(409, "Este pedido já foi concluído ou cancelado")
    try:
        parse_json(body.response)
    except ProviderError as e:
        raise HTTPException(422, "Não encontrei um JSON válido na resposta. Peça ao Claude: 'responda só com o JSON' e cole de novo.") from e
    manual.answer(db, r, body.response)
    audit(db, "manual.answer", user_id=user.id, entity_type="manual_request", entity_id=rid)
    db.commit()
    if r.production_job_id:
        job = db.get(ProductionJob, r.production_job_id)
        if job and job.status == "awaiting_input":
            job.status = "queued"
            db.commit()
            enqueue("advance_production", job.id)
        return {"status": "resumed", "production_id": r.production_job_id}
    if (r.resume or {}).get("kind") == "generate_ideas":
        from app.api.routes.trends_ideas import idea_view
        from app.services.ideas import generate_ideas

        try:
            created = generate_ideas(db, **r.resume["params"])
        except AwaitingManualInput as e:  # resposta inválida: pedido reaberto com a explicação
            db.rollback()
            raise HTTPException(422, e.message) from e
        return {"status": "done", "created": [idea_view(db, i) for i in created]}
    return {"status": "answered"}


@router.post("/manual-requests/{rid}/cancel")
def cancel(rid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    r = get_or_404(db, ManualRequest, rid, "Pedido")
    r.status = "cancelled"
    audit(db, "manual.cancel", user_id=user.id, entity_type="manual_request", entity_id=rid)
    db.commit()
    return view(db, r)


@router.post("/manual-mode")
def set_manual_mode(body: dict, db: Session = Depends(get_db), user: User = Depends(editor)):
    """Liga/desliga o modo 'Claude pela assinatura (copiar e colar)'."""
    rec = db.scalar(select(ModelProvider).where(ModelProvider.adapter == "manual_paste"))
    if not rec:
        raise HTTPException(404, "Provedor copiar e colar não encontrado; reinicie a API para aplicar os dados iniciais")
    rec.is_enabled = bool(body.get("enabled"))
    audit(db, "manual.mode", user_id=user.id, data={"enabled": rec.is_enabled})
    db.commit()
    return {"enabled": rec.is_enabled}
