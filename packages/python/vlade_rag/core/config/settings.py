"""Process configuration.

Values come from environment variables with the ``VLADE_`` prefix. Nested fields use ``__`` as
separator, for example ``VLADE_API__PORT=8000``. See docs/ARCHITECTURE.md section 9.1.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "staging", "prod"]


class ApiSettings(BaseModel):
    """HTTP server settings."""

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    embedded_worker: bool = False


class DatabaseSettings(BaseModel):
    """PostgreSQL. ``url`` uses the application role; ``owner_url`` runs migrations."""

    url: SecretStr | None = None
    owner_url: SecretStr | None = None
    pool_min_size: int = Field(default=1, ge=0)
    pool_max_size: int = Field(default=10, ge=1)


class StorageSettings(BaseModel):
    backend: Literal["postgres", "memory"] = "postgres"


class ObjectStorageSettings(BaseModel):
    backend: Literal["filesystem", "memory"] = "filesystem"
    path: str = "./data/objects"


class OllamaSettings(BaseModel):
    base_url: str = "http://127.0.0.1:11434"
    think: bool | None = None
    timeout: float = 300.0


class OpenAICompatibleSettings(BaseModel):
    base_url: str
    api_key: SecretStr | None = None
    timeout: float = 120.0


class ProvidersSettings(BaseModel):
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    openai: OpenAICompatibleSettings = Field(
        default_factory=lambda: OpenAICompatibleSettings(base_url="https://api.openai.com/v1")
    )
    openrouter: OpenAICompatibleSettings = Field(
        default_factory=lambda: OpenAICompatibleSettings(base_url="https://openrouter.ai/api/v1")
    )
    retries: int = Field(default=3, ge=0, le=10)


class SecuritySettings(BaseModel):
    api_key_pepper: SecretStr | None = None


class WorkerSettings(BaseModel):
    concurrency: int = Field(default=2, ge=1, le=64)
    poll_interval: float = Field(default=1.0, gt=0)
    lease_seconds: int = Field(default=600, ge=10)


class LimitsSettings(BaseModel):
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    max_query_chars: int = Field(default=4000, ge=1)
    max_top_k: int = Field(default=50, ge=1, le=1000)
    job_max_attempts: int = Field(default=3, ge=1)
    store_query_text: bool = False


class OtelSettings(BaseModel):
    enabled: bool = False
    endpoint: str | None = None
    service_name: str = "vlade-rag"


class Settings(BaseSettings):
    """Root settings object."""

    model_config = SettingsConfigDict(
        env_prefix="VLADE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Environment = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api: ApiSettings = Field(default_factory=ApiSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    object_storage: ObjectStorageSettings = Field(default_factory=ObjectStorageSettings)
    providers: ProvidersSettings = Field(default_factory=ProvidersSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    limits: LimitsSettings = Field(default_factory=LimitsSettings)
    otel: OtelSettings = Field(default_factory=OtelSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings, loaded once."""
    return Settings()
