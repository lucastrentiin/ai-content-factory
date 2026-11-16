"""Fluxo de pedidos manuais (copiar e colar) para o LLM."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AwaitingManualInput, ProviderError
from app.core.events import publish_event
from app.models import ManualRequest

TITLES = {
    "write_script": "Roteiro do vídeo", "generate_ideas": "Ideias de conteúdo", "trend_analysis": "Análise de tendências",
    "review_script": "Revisão do roteiro", "fact_check": "Verificação de fatos", "publication_metadata": "Título e legenda",
}


def build_prompt(system: str, prompt: str) -> str:
    return (
        "Você vai me ajudar dentro de uma ferramenta de produção de vídeos. Siga as instruções e responda no formato pedido.\n\n"
        "## INSTRUÇÕES\n" + system.strip() + "\n\n## TAREFA\n" + prompt.strip() +
        "\n\n## FORMATO DA RESPOSTA\nResponda SOMENTE com um único objeto JSON válido, sem nenhum texto antes ou depois. "
        "Pode usar um bloco ```json se preferir. Não use aspas tipográficas nos nomes dos campos."
    )


def handle(db: Session, *, operation: str, system: str, prompt: str, production_job_id: int | None, channel_id: int | None,
           agent: str | None, parse: Callable[[str], Any], resume: dict | None = None) -> Any:
    """Retorna os dados da resposta já colada (validados) ou cria/reabre um pedido e lança AwaitingManualInput."""
    q = select(ManualRequest).where(ManualRequest.operation == operation, ManualRequest.status.in_(["pending", "answered"]))
    q = q.where(ManualRequest.production_job_id == production_job_id) if production_job_id else \
        q.where(ManualRequest.production_job_id.is_(None), ManualRequest.channel_id == channel_id)
    req = db.scalar(q.order_by(ManualRequest.id.desc()).limit(1))
    if req and req.status == "answered":
        try:
            data = parse(req.response or "")
        except (ProviderError, ValueError, KeyError, TypeError) as e:
            req.status = "pending"
            req.error = f"A resposta colada não está no formato esperado: {getattr(e, 'message', str(e))[:400]}. Peça ao Claude para responder só com o JSON e cole de novo."
            db.commit()
            raise AwaitingManualInput(req.id, req.error) from e
        req.status = "consumed"
        db.flush()
        return data
    full = build_prompt(system, prompt)
    if req is None:
        req = ManualRequest(operation=operation, production_job_id=production_job_id, channel_id=channel_id, agent=agent,
                            title=TITLES.get(operation, operation), prompt=full, resume=resume or {})
        db.add(req)
    else:
        req.prompt = full  # mantém o prompt atualizado
        if resume:
            req.resume = resume
    db.commit()
    publish_event("manual.request", {"id": req.id, "operation": operation, "job_id": production_job_id})
    raise AwaitingManualInput(req.id)


def answer(db: Session, req: ManualRequest, text: str) -> None:
    req.response = text.strip()
    req.status = "answered"
    req.error = None
    req.answered_at = datetime.now(UTC)
    db.commit()
