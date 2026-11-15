"""Despacho de tarefas assíncronas (Celery) com modo síncrono para testes/desenvolvimento."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def enqueue(task_name: str, *args: Any, countdown: float | None = None, queue: str | None = None) -> str | None:
    from app.worker import tasks  # import tardio para evitar ciclo

    task = getattr(tasks, task_name)
    if settings.celery_eager:
        if countdown:  # em modo síncrono, re-tentativas agendadas são executadas por quem chamar novamente
            log.info("modo síncrono: ignorando execução agendada", extra={"task": task_name})
            return None
        task.apply(args=args)
        return None
    opts: dict[str, Any] = {}
    if countdown:
        opts["countdown"] = countdown
    if queue:
        opts["queue"] = queue
    res = task.apply_async(args=args, **opts)
    return res.id
