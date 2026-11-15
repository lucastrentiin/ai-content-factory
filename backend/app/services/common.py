"""Serviços transversais: notificações, auditoria, log de sistema, configurações."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import publish_event
from app.core.logging import get_logger
from app.models import AuditLog, Notification, SystemLog, SystemSetting

log = get_logger("factory")

DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "automation": {"factory_enabled": True, "max_concurrent_productions": 2, "ideas_per_run": 8,
                   "min_idea_score_auto": 0.55, "auto_approve_ideas": True},
    "providers": {"allow_simulated": True},
    "learning": {"min_samples": 8, "confidence": 0.9, "exploration_floor": 0.1, "metric": "engagement_score",
                 "max_weight_change": 0.35},
    "quality": {"min_loudness_lufs": -20, "max_loudness_lufs": -10, "max_black_ratio": 0.15, "require_license_check": True},
}


def notify(db: Session, title: str, message: str = "", *, level: str = "info", category: str = "system",
           link: str | None = None, user_id: int | None = None, dedupe_key: str | None = None) -> Notification | None:
    if dedupe_key:
        exists = db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe_key))
        if exists:
            return None
    n = Notification(title=title[:200], message=message, level=level, category=category, link=link,
                     user_id=user_id, dedupe_key=dedupe_key)
    db.add(n)
    db.flush()
    publish_event("notification", {"id": n.id, "title": n.title, "level": level, "category": category})
    return n


def audit(db: Session, action: str, *, user_id: int | None = None, entity_type: str | None = None,
          entity_id: Any = None, data: dict | None = None, ip: str | None = None) -> None:
    db.add(AuditLog(action=action, user_id=user_id, entity_type=entity_type,
                    entity_id=str(entity_id) if entity_id is not None else None, data=data or {}, ip=ip))


def syslog(db: Session, level: str, source: str, message: str, **context: Any) -> None:
    db.add(SystemLog(level=level, source=source, message=message[:5000], context=context))
    getattr(log, level.lower() if level.lower() in ("info", "warning", "error", "debug") else "info")(
        message, extra={"source": source, **{k: v for k, v in context.items() if isinstance(v, (str, int, float, bool))}})


def get_setting(db: Session, key: str) -> dict[str, Any]:
    row = db.get(SystemSetting, key)
    base = dict(DEFAULT_SETTINGS.get(key, {}))
    if row:
        base.update(row.value or {})
    return base


def set_setting(db: Session, key: str, value: dict[str, Any]) -> dict[str, Any]:
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = {**(row.value or {}), **value}
    row.updated_at = datetime.now(UTC)
    db.flush()
    return get_setting(db, key)
