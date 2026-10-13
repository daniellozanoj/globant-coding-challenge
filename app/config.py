"""Application settings loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "dev", "prod"] = "local"
    log_level: str = "INFO"

    # A full URL takes precedence over the individual components.
    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "globant"
    db_user: str = "postgres"
    db_password: str = "postgres"
    # On AWS, Lambdas authenticate with short-lived IAM tokens instead of a password.
    db_iam_auth: bool = False
    db_pool_size: int = Field(default=5, ge=1)

    # Ingestion
    local_data_dir: Path = Path("data")
    max_upload_mb: int = Field(default=50, ge=1)

    # AWS
    aws_region: str = "us-east-1"
    raw_bucket: str | None = None  # enables direct-to-S3 uploads when set
    upload_url_expiration_seconds: int = Field(default=900, ge=60, le=3600)
    # Only on the loader Lambda: mounts POST /internal/events, the AWS Lambda Web Adapter
    # pass-through path for non-HTTP events (SQS messages, migration invocations).
    enable_event_handlers: bool = False

    @property
    def sqlalchemy_url(self) -> str:
        """SQLAlchemy connection URL using the psycopg (v3) driver."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, also usable as a FastAPI dependency."""
    return Settings()
