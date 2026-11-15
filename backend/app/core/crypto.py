"""Criptografia de credenciais em repouso (Fernet / AES-128-CBC + HMAC)."""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    key = settings.secrets_encryption_key
    if not key:
        # Deriva chave determinística de SECRET_KEY (aceitável em dev; em produção defina SECRETS_ENCRYPTION_KEY).
        digest = hashlib.sha256(("fernet:" + settings.secret_key).encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_json(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode()).decode())
    except (InvalidToken, ValueError):
        return {}


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "•" * len(value)
    return value[:3] + "•" * 6 + value[-4:]
