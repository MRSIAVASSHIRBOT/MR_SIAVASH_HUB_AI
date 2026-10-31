"""Centralized application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
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


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings instance."""
    return Settings()
