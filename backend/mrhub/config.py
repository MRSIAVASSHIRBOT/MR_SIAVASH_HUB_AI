"""Centralized application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables and an optional .env file."""

    model_config = SettingsConfigDict(
        env_prefix="MRH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MR_SIAVASH_HUB_AI"
    environment: str = Field(default="development", pattern="^(development|test|production)$")
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database_path: Path = Path("./data/mrhub.sqlite3")
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    session_ttl_hours: int = Field(default=12, ge=1, le=168)
    local_inference_enabled: bool = False
    local_inference_base_url: str = "http://127.0.0.1:11434"
    local_inference_model: str | None = None
    local_inference_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    remote_inference_enabled: bool = False
    remote_inference_api_key: SecretStr | None = None
    remote_inference_model: str | None = None
    remote_inference_base_url: str = "https://openrouter.ai/api/v1"
    remote_inference_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    require_worker_for_readiness: bool = False
    worker_heartbeat_timeout_seconds: int = Field(default=15, ge=3, le=300)
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    instagram_access_token: SecretStr | None = None
    instagram_user_id: str | None = None
    instagram_graph_api_version: str | None = None
    public_media_base_url: str | None = None
    public_media_signing_key: SecretStr | None = None
    # Optional local assistant gateway bridge; disabled unless explicitly configured.
    assistant_gateway_enabled: bool = False
    assistant_gateway_base_url: str | None = None
    assistant_gateway_health_path: str = Field(default="/health", min_length=1, max_length=200)
    assistant_gateway_timeout_seconds: float = Field(default=2.0, ge=0.2, le=10.0)
    assistant_gateway_max_response_bytes: int = Field(default=8192, ge=256, le=16384)


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings instance."""
    return Settings()
