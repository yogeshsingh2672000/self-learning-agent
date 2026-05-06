"""
Central settings for the platform, loaded from environment / .env file.
Single source of truth for all runtime configuration.
"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────
    app_name: str = "Self-Improving Agent Platform"
    debug: bool = False

    # ── Database ─────────────────────────────────────────────────
    database_url: str = "postgresql://user:password@localhost:5432/agent_platform"

    # ── Redis ────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── JWT ──────────────────────────────────────────────────────
    secret_key: str = "change-this-secret-key-in-production-min-32-chars"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ── CORS ─────────────────────────────────────────────────────
    cors_origins: List[str] = ["http://localhost:3000"]

    # ── OpenAI ───────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v


settings = Settings()
