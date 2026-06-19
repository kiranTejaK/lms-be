"""
Application settings loaded from environment variables.

Uses pydantic-settings for type-safe configuration with .env file support.
All settings have sensible defaults for local development.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — values are loaded from .env or environment."""

    # ── Environment ──────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"  # development | staging | production

    # ── Database ─────────────────────────────────────────────────────────
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "password"
    DB_NAME: str = "app_db"

    # ── Redis ────────────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_NAME: str = "0"

    # ── Application ──────────────────────────────────────────────────────
    APP_PREFIX: str = "app"
    CACHE_VERSION: str = "v1"

    # ── Logging ──────────────────────────────────────────────────────────
    LOG_DIR: str = "logs"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True
    LOG_MAX_BYTES: int = 5_000_000
    LOG_BACKUP_COUNT: int = 5
    ENABLE_FILE_LOGGING: bool = True
    ENABLE_CONSOLE_LOGGING: bool = True

    # ── JWT Authentication ───────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRY_IN_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRY_IN_MINUTES: int = 10080  # 7 days

    # ── Email / SMTP (Brevo) ─────────────────────────────────────────────
    BREVO_API_KEY: Optional[str] = None
    BREVO_SMTP_SERVER: str = "smtp-relay.brevo.com"
    BREVO_SMTP_PORT: int = 587
    BREVO_SMTP_USER: Optional[str] = None
    BREVO_SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM_NAME: str = "Learning Platform"
    EMAIL_FROM_EMAIL: str = "noreply@learningplatform.com"
    EMAIL_TEMPLATE_DIR: str = "app/templates"

    # ── AWS S3 ───────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = "us-east-1"
    AWS_S3_BUCKET: Optional[str] = None
    AWS_ENDPOINT_URL: Optional[str] = None

    @property
    def DATABASE_URI(self) -> str:
        """Build the PostgreSQL connection string."""
        return (
            f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

def init_settings():
    return Settings()

# settings = Settings()
settings = init_settings()
