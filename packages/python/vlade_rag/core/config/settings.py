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


class S3Settings(BaseModel):
    """The S3 API of AWS or of any S3-compatible service (ADR-0006)."""

    bucket: str = ""
    endpoint_url: str | None = None  # empty for AWS S3; the URL of an S3-compatible service
    region: str = "us-east-1"
    # Without keys, boto3 uses its default chain (environment, shared files, instance role).
    access_key_id: SecretStr | None = None
    secret_access_key: SecretStr | None = None
    path_style: bool = True  # most S3-compatible services need path-style; AWS accepts it too
    create_bucket: bool = False  # create the bucket at start-up (a local service, not the cloud)
    timeout: float = Field(default=30.0, gt=0)

    @field_validator("endpoint_url", "access_key_id", "secret_access_key", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value


class ObjectStorageSettings(BaseModel):
    backend: Literal["filesystem", "memory", "s3"] = "filesystem"
    path: str = "./data/objects"
    s3: S3Settings = Field(default_factory=S3Settings)


class WebSourceSettings(BaseModel):
    """Seeds and limits of the website connector (ADR-0029)."""

    seeds: list[str] = Field(default_factory=list)
    max_pages: int = Field(default=50, ge=1)
    max_depth: int = Field(default=2, ge=0)


class GoogleDriveSourceSettings(BaseModel):
    """OAuth token and folder of the Drive connector (ADR-0029)."""

    access_token: SecretStr | None = None
    folder_id: str = "root"
    page_size: int = Field(default=100, ge=1, le=1000)
    max_files: int = Field(default=1000, ge=1)

    @field_validator("access_token", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value


class SqlSourceSettings(BaseModel):
    """Connection and query of the external SQL connector (ADR-0029)."""

    url: SecretStr | None = None
    query: str | None = None
    filename_columns: list[str] = Field(default_factory=list)
    max_rows: int = Field(default=1000, ge=1)

    @field_validator("url", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value


class SourcesSettings(BaseModel):
    """Download of a document from an origin URI (ARCHITECTURE section 15).

    ``allowed_domains`` is empty by default, so an ``https://`` URI is refused. Each entry is a
    host name; a subdomain of an entry is also allowed. The download never follows a redirect.
    The nested settings configure the connectors of task 5.2.
    """

    allowed_domains: list[str] = Field(default_factory=list)
    max_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    timeout: float = Field(default=30.0, gt=0)
    web: WebSourceSettings = Field(default_factory=WebSourceSettings)
    google_drive: GoogleDriveSourceSettings = Field(default_factory=GoogleDriveSourceSettings)
    sql: SqlSourceSettings = Field(default_factory=SqlSourceSettings)


class OllamaSettings(BaseModel):
    base_url: str = "http://127.0.0.1:11434"
    think: bool | None = None
    timeout: float = 300.0


class OpenAICompatibleSettings(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr | None = None
    timeout: float = 120.0
    # Send "dimensions" with each embeddings request, so a model with a larger default vector
    # returns the dimension of the knowledge base (OpenAI text-embedding-3 does this). Leave it off
    # for a service that rejects the field.
    embedding_dimensions: bool = False

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value


class OpenRouterSettings(OpenAICompatibleSettings):
    base_url: str = "https://openrouter.ai/api/v1"


class GeminiSettings(OpenAICompatibleSettings):
    """Google Gemini through its OpenAI-compatible endpoint (a Gemini API key)."""

    base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"


class OpenCodeSettings(OpenAICompatibleSettings):
    """OpenCode Zen. Only models served on ``/chat/completions`` work with this adapter."""

    base_url: str = "https://opencode.ai/zen/v1"


class LocalModelsSettings(BaseModel):
    """Models that run inside the process (extra ``local-models``): the local reranker."""

    device: str | None = None  # None: CUDA, MPS or CPU, whichever the library finds
    batch_size: int = Field(default=16, ge=1, le=512)
    max_length: int = Field(default=512, ge=16, le=8192)


class ProvidersSettings(BaseModel):
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    openai: OpenAICompatibleSettings = Field(default_factory=OpenAICompatibleSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    opencode: OpenCodeSettings = Field(default_factory=OpenCodeSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    local_models: LocalModelsSettings = Field(default_factory=LocalModelsSettings)
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
            "gemini": self.gemini,
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


class EvaluationSettings(BaseModel):
    """Registry of datasets for scheduled evaluations (ADR-0011).

    ``datasets_path`` is a directory of the server. A name is a subdirectory with a
    ``questions.jsonl`` file. The caller sends only the name.
    """

    datasets_path: str = "evals/datasets"
    default_k: int = Field(default=10, ge=1, le=100)
    max_items: int = Field(default=1000, ge=1)


class QdrantSettings(BaseModel):
    """Connection to Qdrant, an alternative VectorIndex (ADR-0004)."""

    url: str = "http://localhost:6333"
    api_key: SecretStr | None = None
    timeout: int = Field(default=30, ge=1)
    collection_prefix: str = "vlade_"
    # With published or metadata filters, Qdrant returns more candidates before filtering.
    oversample: int = Field(default=5, ge=1, le=50)

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value


class VectorIndexSettings(BaseModel):
    """pgvector stays the default. Qdrant is optional and needs the "qdrant" extra."""

    backend: Literal["postgres", "qdrant"] = "postgres"
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)


class OtelSettings(BaseModel):
    enabled: bool = False
    endpoint: str | None = None
    service_name: str = "vlade-rag"
    # Send metrics to <endpoint>/v1/metrics. Arize Phoenix takes only traces: turn it off there.
    metrics: bool = True
    # The project of the traces in Arize Phoenix (resource attribute openinference.project.name).
    project: str = "vlade-rag"


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
    vector_index: VectorIndexSettings = Field(default_factory=VectorIndexSettings)
    object_storage: ObjectStorageSettings = Field(default_factory=ObjectStorageSettings)
    providers: ProvidersSettings = Field(default_factory=ProvidersSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    sources: SourcesSettings = Field(default_factory=SourcesSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    limits: LimitsSettings = Field(default_factory=LimitsSettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)
    otel: OtelSettings = Field(default_factory=OtelSettings)
    # Server default for new knowledge bases, as JSON. A config sent on creation is merged
    # over it. Example: {"embeddings": {"provider": "openrouter", ...}, "generation": {...}}
    default_kb_config: dict[str, Any] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings, loaded once."""
    return Settings()
