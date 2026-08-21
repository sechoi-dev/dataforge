from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from DATAFORGE_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="DATAFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DataForge"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+psycopg://dataforge:dataforge@localhost:5432/dataforge"
    )
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "dataforge"
    minio_secret_key: str = "dataforge-dev-password"
    minio_secure: bool = False
    minio_bucket: str = "dataforge"
    maximum_upload_size_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    maximum_rows: int = Field(default=1_000_000, gt=0)
    maximum_columns: int = Field(default=1_000, gt=0)
    maximum_report_size_bytes: int = Field(default=5 * 1024 * 1024, gt=0)
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)


@lru_cache
def get_settings() -> Settings:
    return Settings()
