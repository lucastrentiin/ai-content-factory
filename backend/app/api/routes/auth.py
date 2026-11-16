from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import COOKIE, client_ip, current_user
from app.api.utils import serialize
from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import LoginIn, PasswordChangeIn
from app.services.common import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def is_https(request: Request) -> bool:
    """Cookie 'Secure' só quando o navegador acessa por HTTPS (direto, via Caddy ou via Cloudflare/túnel).
    Acesso pela rede local em http://IP continua funcionando."""
    if request.url.scheme == "https":
        return True
    proto = request.headers.get("x-forwarded-proto", "").lower()
    visitor = request.headers.get("cf-visitor", "").lower()
    return "https" in proto or '"https"' in visitor


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(db, "auth.login_failed", data={"email": body.email}, ip=client_ip(request))
        db.commit()
        raise HTTPException(401, "E-mail ou senha inválidos")
    user.last_login_at = datetime.now(UTC)
    token = create_access_token(user.id, user.role)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=is_https(request),
                        max_age=settings.access_token_minutes * 60, path="/")
    audit(db, "auth.login", user_id=user.id, ip=client_ip(request))
    db.commit()
    return {"access_token": token, "token_type": "bearer", "user": serialize(user)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return serialize(user)


@router.post("/change-password")
def change_password(body: PasswordChangeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Senha atual incorreta")
    user.password_hash = hash_password(body.new_password)
    audit(db, "auth.password_changed", user_id=user.id)
    db.commit()
    return {"ok": True}
