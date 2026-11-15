"""Configuração central carregada de variáveis de ambiente (.env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Aplicação
    app_name: str = "AI Content Factory"
    app_env: str = Field(default="development", description="development | production | test")
    secret_key: str = Field(default="change-me-in-production-please-32chars", min_length=16)
    secrets_encryption_key: str = Field(
        default="",
        description="Chave Fernet (base64 32 bytes) para criptografar credenciais. Gerada a partir de SECRET_KEY se vazia.",
    )
    access_token_minutes: int = 60 * 12
    public_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000"]
    log_level: str = "INFO"
    log_json: bool = True

    # Primeiro administrador (criado no bootstrap se não houver usuários)
    first_admin_email: str = "admin@example.com"
    first_admin_password: str = "admin12345"

    # Infra
    database_url: str = "postgresql+psycopg://factory:factory@localhost:5432/factory"
    redis_url: str = "redis://localhost:6379/0"
    celery_eager: bool = False

    # Storage
    storage_backend: str = "local"  # local | s3
    storage_local_path: Path = Path("./data/storage")
    s3_endpoint_url: str | None = None
    s3_public_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "content-factory"
    s3_region: str = "us-east-1"

    # Diretório de trabalho temporário de renderização
    work_dir: Path = Path("./data/work")

    # Provedores simulados (claramente identificados) para operar sem credenciais
    allow_simulated_providers: bool = True

    # Credenciais opcionais via ambiente (também podem ser cadastradas na interface, criptografadas)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openrouter_api_key: str | None = None
    ollama_base_url: str | None = None
    elevenlabs_api_key: str | None = None
    stability_api_key: str | None = None
    replicate_api_token: str | None = None
    youtube_api_key: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    tiktok_client_key: str | None = None
    tiktok_client_secret: str | None = None
    meta_app_id: str | None = None
    meta_app_secret: str | None = None

    # Limites operacionais
    api_rate_limit_per_minute: int = 240
    login_rate_limit_per_minute: int = 10
    render_timeout_s: int = 1800

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
