"""Utilitários de serialização e paginação."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

SENSITIVE = {"password_hash", "credentials_encrypted", "token_hash"}


def serialize(obj: Any, *, exclude: set[str] | None = None, extra: dict | None = None) -> dict[str, Any]:
    if obj is None:
        return None  # type: ignore[return-value]
    out = {}
    for col in obj.__table__.columns:
        k = col.key
        if k in SENSITIVE or (exclude and k in exclude):
            continue
        v = getattr(obj, k)
        out[k] = v.isoformat() if isinstance(v, (datetime, date)) else v
    if extra:
        out.update(extra)
    return out


def page(db: Session, query, *, limit: int, offset: int, mapper=serialize) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = db.scalars(query.limit(min(limit, 500)).offset(offset)).all()
    return {"items": [mapper(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def get_or_404(db: Session, model, id_: int, label: str = "Registro"):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{label} não encontrado")
    return obj


def apply_updates(obj: Any, data: dict[str, Any]) -> Any:
    for k, v in data.items():
        if hasattr(obj, k):
            setattr(obj, k, v)
    return obj
