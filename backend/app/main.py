"""Aplicação FastAPI."""
from __future__ import annotations

import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.middleware import RateLimitMiddleware
from app.api.routes import (
    admin,
    analytics,
    auth,
    channels,
    content,
    library,
    manual,
    production,
    publishing,
    trends_ideas,
    ws,
)
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import (
    AwaitingManualInput,
    BudgetExceeded,
    Conflict,
    FactoryError,
    MissingCredentials,
    NotFound,
    ValidationFailed,
)
from app.core.events import redis_client
from app.core.logging import get_logger, setup_logging
from app.storage import get_storage

setup_logging()
log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    if settings.is_production and settings.secret_key.startswith("change-me"):
        log.error("SECRET_KEY padrão em produção! Defina SECRET_KEY no .env")
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

STATUS = {AwaitingManualInput: 202, NotFound: 404, ValidationFailed: 422, Conflict: 409, BudgetExceeded: 402, MissingCredentials: 424}


@app.exception_handler(FactoryError)
async def factory_error_handler(_req: Request, exc: FactoryError):
    code = next((v for k, v in STATUS.items() if isinstance(exc, k)), 400)
    return JSONResponse({"detail": exc.message, "code": exc.code, "details": exc.details}, status_code=code)


@app.exception_handler(RequestValidationError)
async def validation_handler(_req: Request, exc: RequestValidationError):
    errs = [{"field": ".".join(str(x) for x in e["loc"][1:]), "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse({"detail": "Dados inválidos", "errors": errs}, status_code=422)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/api/health/ready", tags=["system"])
def ready():
    checks = {}
    try:
        with SessionLocal() as db:
            db.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"erro: {e}"[:200]
    try:
        redis_client().ping()
        checks["redis"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"erro: {e}"[:200]
    checks["storage"] = "ok" if get_storage().healthcheck() else "erro"
    checks["ffmpeg"] = "ok" if shutil.which("ffmpeg") else "ausente"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)


for r in (auth.router, channels.router, trends_ideas.router, content.router, library.router, production.router,
          publishing.router, analytics.router, admin.router, manual.router, ws.router):
    app.include_router(r, prefix="/api")
