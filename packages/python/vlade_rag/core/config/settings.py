"""Process configuration.

Values come from environment variables with the ``VLADE_`` prefix. Nested fields use ``__`` as
separator, for example ``VLADE_API__PORT=8000``. See docs/ARCHITECTURE.md section 9.1.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
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
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr | None = None
    timeout: float = 120.0

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value


class OpenRouterSettings(OpenAICompatibleSettings):
    base_url: str = "https://openrouter.ai/api/v1"


class OpenCodeSettings(OpenAICompatibleSettings):
    """OpenCode Zen. Only models served on ``/chat/completions`` work with this adapter."""

    base_url: str = "https://opencode.ai/zen/v1"


class ProvidersSettings(BaseModel):
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    openai: OpenAICompatibleSettings = Field(default_factory=OpenAICompatibleSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    opencode: OpenCodeSettings = Field(default_factory=OpenCodeSettings)
    # Any other OpenAI-compatible API, by name. Example:
    # VLADE_PROVIDERS__COMPATIBLE__GROQ__BASE_URL=https://api.groq.com/openai/v1
    # VLADE_PROVIDERS__COMPATIBLE__GROQ__API_KEY=...
    # The knowledge base then uses provider "groq".
    compatible: dict[str, OpenAICompatibleSettings] = Field(default_factory=dict)

    def openai_compatible(self) -> dict[str, OpenAICompatibleSettings]:
        """Every OpenAI-compatible provider by name: built-in ones and ``compatible``."""
        return {
            "openai": self.openai,
            "openrouter": self.openrouter,
            "opencode": self.opencode,
            **{name.lower(): cfg for name, cfg in self.compatible.items()},
        }

    retries: int = Field(default=3, ge=0, le=10)


class SecuritySettings(BaseModel):
    api_key_pepper: SecretStr | None = None


class WorkerSettings(BaseModel):
    concurrency: int = Field(default=2, ge=1, le=64)
    poll_interval: float = Field(default=1.0, gt=0)
    lease_seconds: int = Field(default=600, ge=10)


class CacheSettings(BaseModel):
    """Valkey or Redis (ADR-0007). Without ``url``, cache and rate limit live in the process."""

    url: SecretStr | None = None

    @field_validator("url", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value


class LimitsSettings(BaseModel):
    # Token bucket per API key and per tenant, in requests per minute. 0 turns the limit off.
    rate_per_key_per_minute: int = Field(default=600, ge=0)
    rate_per_tenant_per_minute: int = Field(default=3000, ge=0)
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
    cache: CacheSettings = Field(default_factory=CacheSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    limits: LimitsSettings = Field(default_factory=LimitsSettings)
    otel: OtelSettings = Field(default_factory=OtelSettings)
    # Server default for new knowledge bases, as JSON. A config sent on creation is merged
    # over it. Example: {"embeddings": {"provider": "openrouter", ...}, "generation": {...}}
    default_kb_config: dict[str, Any] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings, loaded once."""
    return Settings()
