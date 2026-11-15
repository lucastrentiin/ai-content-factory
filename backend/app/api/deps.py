"""Dependências da API: sessão de banco, usuário autenticado (JWT em cookie/Bearer ou token de API), papéis."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token, hash_api_token
from app.models import ApiToken, User

COOKIE = "cf_session"
ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}


def _token_from(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE)


def resolve_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    if token.startswith("cf_"):
        t = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_api_token(token), ApiToken.revoked.is_(False)))
        if not t:
            return None
        t.last_used_at = datetime.now(UTC)
        db.commit()
        user = db.get(User, t.user_id)
    else:
        data = decode_access_token(token)
        if not data:
            return None
        user = db.get(User, int(data["sub"]))
    return user if user and user.is_active else None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = resolve_user(db, _token_from(request))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado")
    request.state.user_id = user.id
    return user


def require(role: str) -> Callable[..., User]:
    def dep(user: User = Depends(current_user)) -> User:
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK[role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permissão insuficiente")
        return user

    return dep


viewer = require("viewer")
editor = require("editor")
admin = require("admin")


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")
