"""Registro de arquivos no storage + metadados no banco. Organização: canal/série/produção/tipo."""
from __future__ import annotations

import hashlib
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import Asset
from app.storage import get_storage


def build_key(*, kind: str, name: str, channel_id: int | None = None, series_id: int | None = None,
              production_job_id: int | None = None, prefix: str | None = None) -> str:
    parts: list[str] = []
    if prefix:
        parts.append(prefix)
    else:
        parts.append(f"channels/{channel_id}" if channel_id else "library")
        if series_id:
            parts.append(f"series/{series_id}")
        if production_job_id:
            parts.append(f"productions/{production_job_id}")
    parts.append(kind)
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:80] or "file"
    parts.append(f"{uuid.uuid4().hex[:12]}_{safe}")
    return "/".join(parts)


def store_asset(db: Session, *, kind: str, name: str, data: bytes | None = None, path: Path | None = None,
                mime: str | None = None, origin: str = "generated", license: str = "internal_generated",
                license_note: str = "", provider_key: str | None = None, model: str | None = None, prompt: str | None = None,
                channel_id: int | None = None, series_id: int | None = None, production_job_id: int | None = None,
                is_simulated: bool = False, is_reusable: bool = False, tags: list | None = None, meta: dict | None = None,
                width: int | None = None, height: int | None = None, duration_s: float | None = None,
                key_prefix: str | None = None) -> Asset:
    if data is None and path is None:
        raise ValueError("data ou path é obrigatório")
    mime = mime or mimetypes.guess_type(name)[0] or "application/octet-stream"
    key = build_key(kind=kind, name=name, channel_id=channel_id, series_id=series_id,
                    production_job_id=production_job_id, prefix=key_prefix)
    storage = get_storage()
    if data is not None:
        checksum = hashlib.sha256(data).hexdigest()
        size = len(data)
        storage.put_bytes(data, key, mime)
    else:
        assert path is not None
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        checksum = h.hexdigest()
        size = path.stat().st_size
        storage.put_file(path, key, mime)
    a = Asset(kind=kind, name=name, storage_key=key, mime=mime, size_bytes=size, checksum=checksum, origin=origin,
              license=license, license_note=license_note, provider_key=provider_key, model=model, prompt=prompt,
              channel_id=channel_id, series_id=series_id, production_job_id=production_job_id, is_simulated=is_simulated,
              is_reusable=is_reusable, tags=tags or [], meta=meta or {}, width=width, height=height, duration_s=duration_s)
    db.add(a)
    db.flush()
    return a


def fetch_to(asset: Asset, dest_dir: Path) -> Path:
    """Baixa o asset para um diretório de trabalho (cache por chave)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"a{asset.id}_{Path(asset.storage_key).name}"
    if not dest.exists() or dest.stat().st_size != asset.size_bytes:
        get_storage().download(asset.storage_key, dest)
    return dest


def read_asset(asset: Asset) -> bytes:
    return get_storage().read_bytes(asset.storage_key)


def asset_url(asset: Asset | None) -> str | None:
    return f"/api/assets/{asset.id}/file" if asset else None


def asset_public(asset: Asset) -> dict[str, Any]:
    return {"id": asset.id, "kind": asset.kind, "name": asset.name, "mime": asset.mime, "url": asset_url(asset),
            "width": asset.width, "height": asset.height, "duration_s": asset.duration_s, "size_bytes": asset.size_bytes,
            "license": asset.license, "is_simulated": asset.is_simulated, "origin": asset.origin}
