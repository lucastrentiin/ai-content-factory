"""Rate limit (janela fixa em Redis) e log de requisições."""
from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.events import redis_client
from app.core.logging import get_logger

log = get_logger("http")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/api") and not path.startswith(("/api/health", "/api/assets/")) and request.method != "OPTIONS":
            ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
            is_login = path == "/api/auth/login"
            limit = settings.login_rate_limit_per_minute if is_login else settings.api_rate_limit_per_minute
            key = f"rl:{'login' if is_login else 'api'}:{ip}:{int(time.time() // 60)}"
            try:
                r = redis_client()
                n = r.incr(key)
                if n == 1:
                    r.expire(key, 70)
                if n > limit:
                    return JSONResponse({"detail": "Muitas requisições. Tente novamente em instantes."}, status_code=429,
                                        headers={"Retry-After": "60"})
            except Exception:  # noqa: BLE001 — sem Redis, não bloqueia a API
                pass
        t0 = time.time()
        response = await call_next(request)
        if path.startswith("/api") and not path.startswith("/api/health"):
            log.info("request", extra={"method": request.method, "path": path, "status": response.status_code,
                                       "ms": int((time.time() - t0) * 1000)})
        return response
