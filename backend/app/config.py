"""Application configuration, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("meetpilot.config")

_DEV_ENVS = {"development", "test"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    # --- Core -------------------------------------------------------------------------------
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/meetpilot.db"
    secret_key: str = ""
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    access_token_minutes: int = Field(default=720, ge=5, le=60 * 24 * 14)
    log_level: str = "INFO"
    serve_frontend_dir: str = ""  # optional: path to a built frontend to serve from the API

    # --- Storage ----------------------------------------------------------------------------
    storage_provider: Literal["local", "s3"] = "local"
    storage_root: str = "./data/storage"
    storage_persistent: bool = True
    database_persistent: bool = True  # false: the database itself is temporary (e.g. SQLite on an ephemeral disk)
    s3_bucket: str = ""
    s3_region: str = ""
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_prefix: str = "meetpilot/"
    max_audio_size_mb: int = Field(default=200, ge=1, le=2048)
    max_audio_duration_minutes: int = Field(default=240, ge=1, le=24 * 60)

    # --- Transcription ----------------------------------------------------------------------
    transcription_provider: Literal["none", "openai", "local"] = "none"
    transcription_api_key: str = ""
    transcription_model: str = ""
    transcription_diarize: bool = True
    transcription_language: str = ""
    transcription_chunk_seconds: int = Field(default=1200, ge=60, le=6 * 3600)
    transcription_timeout_seconds: int = Field(default=900, ge=30)
    local_whisper_model: str = "tiny"
    local_whisper_compute_type: str = "int8"
    local_whisper_threads: int = Field(default=2, ge=1, le=64)
    local_whisper_model_dir: str = ""

    # --- AI analysis ------------------------------------------------------------------------
    ai_provider: Literal["none", "openai", "anthropic", "gemini"] = "none"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_fallback_providers: str = ""  # comma separated, e.g. "gemini,openai"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    ai_max_input_chars: int = Field(default=120_000, ge=2_000)
    ai_timeout_seconds: int = Field(default=300, ge=10)
    auto_analyze: bool = True

    # --- Background jobs --------------------------------------------------------------------
    embedded_worker: bool = True
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    job_timeout_seconds: int = Field(default=3600, ge=60)
    worker_poll_seconds: float = Field(default=2.0, ge=0.1)
    retention_sweep_minutes: int = Field(default=60, ge=1)

    # --- Misc -------------------------------------------------------------------------------
    rate_limit_enabled: bool = True
    demo_enabled: bool = True
    password_reset_minutes: int = 30
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        # Render and Heroku style URLs use postgres:// - SQLAlchemy needs an explicit driver.
        if v.startswith("postgres://"):
            v = "postgresql+psycopg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_audio_bytes(self) -> int:
        return self.max_audio_size_mb * 1024 * 1024

    @property
    def fallback_provider_list(self) -> list[str]:
        out: list[str] = []
        for p in self.ai_fallback_providers.split(","):
            p = p.strip().lower()
            if p and p != self.ai_provider and p in {"openai", "anthropic", "gemini"} and p not in out:
                out.append(p)
        return out

    def provider_key(self, provider: str) -> str:
        """API key for an AI provider. AI_API_KEY applies to the primary provider only."""
        if provider == self.ai_provider and self.ai_api_key:
            return self.ai_api_key
        return {"openai": self.openai_api_key, "anthropic": self.anthropic_api_key,
                "gemini": self.gemini_api_key}.get(provider, "")

    @property
    def transcription_key(self) -> str:
        return self.transcription_api_key or (self.openai_api_key if self.transcription_provider == "openai" else "")


_ephemeral_key: str | None = None


def resolve_secret_key(settings: Settings) -> str:
    """Return the signing key. Production refuses to start without a strong one."""
    global _ephemeral_key
    if settings.secret_key and len(settings.secret_key) >= 32:
        return settings.secret_key
    if settings.is_production:
        raise RuntimeError("SECRET_KEY must be set to a random value of at least 32 characters in production.")
    if _ephemeral_key is None:
        _ephemeral_key = secrets.token_urlsafe(48)
        if settings.environment != "test":
            log.warning("SECRET_KEY is not set: using a temporary key. Everyone is signed out when the server restarts.")
    return _ephemeral_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
