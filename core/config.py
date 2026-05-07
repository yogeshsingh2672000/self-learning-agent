"""
Central settings for the platform, loaded from environment / .env file.
Single source of truth for all runtime configuration.
"""
import os
from pathlib import Path
from typing import List, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

# Get the absolute path to the .env file (in the backend directory)
BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
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

    # ── GitHub (Phase 6) ─────────────────────────────────────────
    github_token: str = ""
    github_repo: str = ""  # format: "owner/repo"
    github_webhook_secret: str = ""

    # ── Phase 8: Hardening & Production Readiness ─────────────────
    # Rate Limiting
    daily_gap_limit: int = 10  # Max capability gap tasks per day
    gap_rate_limit_hours: int = 24  # Time window for rate limiting

    # Cost Controls
    daily_token_budget: int = 100000  # Max tokens per day
    cost_alert_threshold: float = 0.8  # Alert at 80% of budget

    # Circuit Breaker
    failure_threshold: int = 4  # Escalate after N failures (read from FAILURE_THRESHOLD in .env)
    
    # Notifications (Phase 8)
    enable_email_notifications: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    notification_from_email: str = "noreply@agent-platform.local"
    notification_to_emails: Union[str, List[str]] = ""  # Comma-separated or list
    
    # Slack (optional)
    slack_webhook_url: str = ""  # For Slack notifications
    slack_channel: str = "#agent-notifications"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @field_validator("notification_to_emails", mode="before")
    @classmethod
    def parse_emails(cls, v):
        if isinstance(v, str):
            return [e.strip() for e in v.split(",") if e.strip()]
        return v or []
    
    def get_notification_emails(self) -> List[str]:
        """Parse notification_to_emails as a list."""
        if isinstance(self.notification_to_emails, list):
            return self.notification_to_emails
        return [e.strip() for e in str(self.notification_to_emails).split(",") if e.strip()]


settings = Settings()
