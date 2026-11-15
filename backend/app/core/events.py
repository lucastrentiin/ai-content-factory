"""Eventos em tempo real via Redis Pub/Sub (consumidos pelo WebSocket da API)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import redis

from app.core.config import settings
from app.core.logging import get_logger

CHANNEL = "factory:events"
log = get_logger(__name__)


@lru_cache
def redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=5)


def publish_event(event_type: str, data: dict[str, Any] | None = None) -> None:
    payload = {"type": event_type, "ts": datetime.now(UTC).isoformat(), "data": data or {}}
    try:
        redis_client().publish(CHANNEL, json.dumps(payload, default=str))
    except Exception as exc:  # eventos são best-effort; nunca quebram o fluxo principal
        log.debug("falha ao publicar evento", extra={"error": str(exc)})
