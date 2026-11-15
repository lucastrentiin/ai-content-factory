from celery import Celery

from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()
celery = Celery("factory", broker=settings.redis_url, backend=settings.redis_url, include=["app.worker.tasks"])
celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_always_eager=settings.celery_eager,
    task_default_queue="default",
    task_routes={"app.worker.tasks.advance_production": {"queue": "render"}},
    broker_connection_retry_on_startup=True,
    result_expires=3600 * 24,
    timezone="UTC",
    beat_schedule={"scheduler-tick": {"task": "app.worker.tasks.scheduler_tick", "schedule": 60.0}},
)
