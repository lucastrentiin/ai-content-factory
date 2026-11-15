"""Autenticação: hashing de senha (Argon2), JWT e tokens de API."""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: int, role: str, minutes: int | None = None) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes or settings.access_token_minutes)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return data if data.get("typ") == "access" else None
    except jwt.PyJWTError:
        return None


def generate_api_token() -> tuple[str, str]:
    """Retorna (token em claro, hash). O token em claro é exibido uma única vez."""
    raw = "cf_" + secrets.token_urlsafe(32)
    return raw, hash_api_token(raw)


def hash_api_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def sign_state(data: str) -> str:
    """Assinatura HMAC para o parâmetro `state` de fluxos OAuth."""
    import hmac

    mac = hmac.new(settings.secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{data}.{mac}"


def verify_state(state: str) -> str | None:
    import hmac

    if "." not in state:
        return None
    data, mac = state.rsplit(".", 1)
    expected = hmac.new(settings.secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()[:32]
    return data if hmac.compare_digest(mac, expected) else None
