import os
from functools import lru_cache
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env file."""

    # Project metadata
    PROJECT_NAME: str = "AI Chief of Staff"
    VERSION: str = "0.2.0"
    ENVIRONMENT: str = "development"

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "info"

    # Groq LLM settings
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_TIMEOUT_SECONDS: float = 30.0

    # Database settings (PostgreSQL via asyncpg default, SQLite async fallback for tests/local)
    DATABASE_URL: str = "sqlite+aiosqlite:///./chief_of_staff.db"
    DB_ECHO: bool = False

    # Security
    SECRET_KEY: str = "development-secret-key-change-in-production-2026"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    model_config = SettingsConfigDict(
        env_file=(
            Path(__file__).parent.parent.parent / ".env",
            Path(__file__).parent.parent.parent / ".venv" / ".env",
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
