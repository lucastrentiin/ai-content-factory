"""Contrato comum para integrações de publicação (APIs oficiais)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.errors import IntegrationNotAuthorized


@dataclass
class PublishRequest:
    video_path: Path
    cover_path: Path | None
    title: str
    description: str
    hashtags: list[str]
    privacy: str = "public"
    public_video_url: str | None = None
    public_cover_url: str | None = None
    ai_generated: bool = True


@dataclass
class PublishResult:
    status: str  # published | processing | failed
    external_id: str | None = None
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class Metrics:
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    followers_gained: int = 0
    avg_watch_time_s: float | None = None
    completion_rate: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class SocialPlatform:
    key: str = ""
    name: str = ""
    docs: str = ""

    def app_configured(self) -> tuple[bool, str]:
        raise NotImplementedError

    def auth_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Retorna dict com credenciais (tokens) e informações da conta: {creds:{...}, account:{id,name}, expires_in}."""
        raise NotImplementedError

    def refresh(self, creds: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def publish(self, creds: dict[str, Any], config: dict[str, Any], req: PublishRequest) -> PublishResult:
        raise NotImplementedError

    def check_status(self, creds: dict[str, Any], config: dict[str, Any], external_ref: str) -> PublishResult:
        return PublishResult(status="published", external_id=external_ref)

    def fetch_metrics(self, creds: dict[str, Any], config: dict[str, Any], external_id: str) -> Metrics:
        raise NotImplementedError

    @staticmethod
    def expires_at(expires_in: int | None) -> datetime | None:
        return datetime.now(UTC) + timedelta(seconds=int(expires_in)) if expires_in else None

    def require(self, creds: dict, key: str = "access_token") -> str:
        v = creds.get(key)
        if not v:
            raise IntegrationNotAuthorized(f"{self.name}: conta não conectada (token ausente)")
        return v


def caption(description: str, hashtags: list[str], limit: int) -> str:
    tags = " ".join(h if h.startswith("#") else f"#{h}" for h in hashtags)
    text = f"{description.strip()}\n\n{tags}".strip()
    return text[:limit]
