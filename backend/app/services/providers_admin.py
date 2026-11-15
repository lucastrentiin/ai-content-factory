"""Administração de provedores: status (configurado / faltam credenciais / indisponível / simulado), credenciais
criptografadas (nunca retornadas ao frontend), teste de conectividade."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json, encrypt_json, mask_secret
from app.models import ModelProvider, ProviderModel
from app.providers.registry import ADAPTERS, ENV_CREDENTIALS, build_provider


def provider_view(db: Session, rec: ModelProvider) -> dict[str, Any]:
    prov = build_provider(db, rec)
    st = prov.status()
    stored = decrypt_json(rec.credentials_encrypted)
    env = {k for k, v in ENV_CREDENTIALS.get(rec.key, {}).items() if v}
    required = list(ADAPTERS[rec.adapter].required_credentials) or (["api_key"] if rec.adapter == "openai_compatible" and (rec.config or {}).get("requires_api_key", True) else [])
    models = db.scalars(select(ProviderModel).where(ProviderModel.provider_id == rec.id).order_by(ProviderModel.model_key)).all()
    circuit_open = bool(rec.circuit_open_until and rec.circuit_open_until > datetime.now(UTC))
    status = "disabled" if not rec.is_enabled else ("circuit_open" if circuit_open else st.status)
    return {
        "id": rec.id, "key": rec.key, "name": rec.name, "kind": rec.kind, "adapter": rec.adapter, "is_enabled": rec.is_enabled,
        "is_simulated": rec.is_simulated, "priority": rec.priority, "status": status, "status_detail": st.detail or rec.status_detail,
        "config": {k: v for k, v in (rec.config or {}).items() if "key" not in k.lower() and "secret" not in k.lower()},
        "credentials": {k: {"configured": bool(stored.get(k)) or k in env, "source": "env" if k in env and not stored.get(k) else ("db" if stored.get(k) else None),
                            "masked": mask_secret(stored.get(k)) if stored.get(k) else None} for k in required},
        "required_credentials": required, "docs_url": rec.docs_url, "commercial_use_note": rec.commercial_use_note,
        "consecutive_failures": rec.consecutive_failures, "circuit_open_until": rec.circuit_open_until, "last_check_at": rec.last_check_at,
        "models": [{"id": m.id, "model_key": m.model_key, "display_name": m.display_name, "pricing": m.pricing, "quality_score": m.quality_score,
                    "speed_score": m.speed_score, "is_default": m.is_default, "is_enabled": m.is_enabled} for m in models],
    }


def set_credentials(db: Session, rec: ModelProvider, creds: dict[str, str | None]) -> None:
    stored = decrypt_json(rec.credentials_encrypted)
    for k, v in creds.items():
        if v is None or v == "":
            stored.pop(k, None)
        else:
            stored[k] = v.strip()
    rec.credentials_encrypted = encrypt_json(stored) if stored else None
    rec.consecutive_failures = 0
    rec.circuit_open_until = None
    db.flush()


def refresh_status(db: Session, live: bool = False) -> dict:
    out = {}
    for rec in db.scalars(select(ModelProvider)).all():
        prov = build_provider(db, rec)
        st = prov.healthcheck() if live else prov.status()
        rec.status, rec.status_detail, rec.last_check_at = st.status, st.detail, datetime.now(UTC)
        out[rec.key] = st.status
    db.commit()
    return out


def test_provider(db: Session, rec: ModelProvider) -> dict:
    prov = build_provider(db, rec)
    st = prov.healthcheck()
    rec.status, rec.status_detail, rec.last_check_at = st.status, st.detail, datetime.now(UTC)
    if st.ok:
        rec.consecutive_failures, rec.circuit_open_until = 0, None
    db.commit()
    return {"ok": st.ok, "status": st.status, "detail": st.detail}
