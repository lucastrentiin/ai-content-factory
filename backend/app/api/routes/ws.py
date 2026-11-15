"""WebSocket de eventos em tempo real (Redis Pub/Sub → navegador)."""
from __future__ import annotations

import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import COOKIE, resolve_user
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.events import CHANNEL

router = APIRouter()


@router.websocket("/ws")
async def events(ws: WebSocket):
    token = ws.query_params.get("token") or ws.cookies.get(COOKIE)
    with SessionLocal() as db:
        user = resolve_user(db, token)
    if not user:
        await ws.close(code=4401)
        return
    await ws.accept()
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(CHANNEL)
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=20)
            if msg and msg.get("type") == "message":
                await ws.send_text(msg["data"])
            else:
                await ws.send_text('{"type":"ping"}')
            await asyncio.sleep(0.05)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await pubsub.unsubscribe(CHANNEL)
        await r.aclose()
