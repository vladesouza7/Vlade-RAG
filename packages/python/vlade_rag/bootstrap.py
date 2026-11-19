"""Composition root: build the ``Dependencies`` of the use cases from ``Settings``.

Built-in adapters register here. External adapters register through the entry point group
``vlade_rag.plugins`` (see ``vlade_rag.core.registry``). The API, the CLI and the worker build
one ``Runtime`` per process and close it at shutdown.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from vlade_rag.core.application import Dependencies, Limits
from vlade_rag.core.config import Settings, get_settings
from vlade_rag.core.domain import InvalidArgument
from vlade_rag.core.domain.kb_config import EmbeddingsConfig, GenerationConfig
from vlade_rag.core.ports import (
    DocumentParser,
    EmbeddingProvider,
    LLMProvider,
    TenantDirectory,
    Tracer,
)
from vlade_rag.core.registry import PluginSpec, Registry
from vlade_rag.embeddings.hashing import HashingEmbeddingProvider
from vlade_rag.generation.prompts import BuiltinPromptRegistry
from vlade_rag.generation.providers.extractive import ExtractiveLLM
from vlade_rag.ingestion.chunking import NativeChunker, NativeTextNormalizer
from vlade_rag.ingestion.parsers.basic import basic_parsers
from vlade_rag.retrieval.fusion import RRFFusion

Closer = Callable[[], Awaitable[None]]


class ProviderClients:
    """Lazy, shared HTTP clients per provider (one connection pool each)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._clients: dict[str, Any] = {}

    def get(self, provider: str) -> Any:
        if provider in self._clients:
            return self._clients[provider]
        from vlade_rag.integrations.external.http import ProviderHttpClient

        p = self.settings.providers
        if provider == "ollama":
            client = ProviderHttpClient(
                "ollama", p.ollama.base_url, timeout=p.ollama.timeout, retries=p.retries
            )
        elif provider in ("openai", "openrouter"):
            cfg = p.openai if provider == "openai" else p.openrouter
            headers = {}
            if cfg.api_key is not None:
                headers["Authorization"] = f"Bearer {cfg.api_key.get_secret_value()}"
            client = ProviderHttpClient(
                provider, cfg.base_url, headers=headers, timeout=cfg.timeout, retries=p.retries
            )
        else:
            raise InvalidArgument(f"Provider '{provider}' has no HTTP client.")
        self._clients[provider] = client
        return client

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()


def builtin_plugins() -> list[PluginSpec]:
    def ollama_embeddings(cfg: EmbeddingsConfig, clients: ProviderClients) -> EmbeddingProvider:
        from vlade_rag.generation.providers.ollama import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider(clients.get("ollama"), cfg.model, cfg.dimension)

    def openai_embeddings(provider: str) -> Callable[..., EmbeddingProvider]:
        def factory(cfg: EmbeddingsConfig, clients: ProviderClients) -> EmbeddingProvider:
            from vlade_rag.generation.providers.openai_compatible import (
                OpenAICompatibleEmbeddingProvider,
            )

            return OpenAICompatibleEmbeddingProvider(
                clients.get(provider), provider, cfg.model, cfg.dimension
            )

        return factory

    def ollama_llm(cfg: GenerationConfig, clients: ProviderClients) -> LLMProvider:
        from vlade_rag.generation.providers.ollama import OllamaLLM

        return OllamaLLM(clients.get("ollama"), think=clients.settings.providers.ollama.think)

    def openai_llm(provider: str) -> Callable[..., LLMProvider]:
        def factory(cfg: GenerationConfig, clients: ProviderClients) -> LLMProvider:
            from vlade_rag.generation.providers.openai_compatible import OpenAICompatibleLLM

            return OpenAICompatibleLLM(clients.get(provider), provider)

        return factory

    return [
        PluginSpec("embeddings", "ollama", ollama_embeddings, "Ollama /api/embed"),
        PluginSpec("embeddings", "openai", openai_embeddings("openai"), "OpenAI API"),
        PluginSpec("embeddings", "openrouter", openai_embeddings("openrouter"), "OpenRouter"),
        PluginSpec(
            "embeddings",
            "hashing",
            lambda cfg, clients: HashingEmbeddingProvider(cfg.model, cfg.dimension),
            "Offline feature hashing (tests and demos)",
        ),
        PluginSpec("llm", "ollama", ollama_llm, "Ollama /api/chat"),
        PluginSpec("llm", "openai", openai_llm("openai"), "OpenAI API"),
        PluginSpec("llm", "openrouter", openai_llm("openrouter"), "OpenRouter"),
        PluginSpec(
            "llm",
            "extractive",
            lambda cfg, clients: ExtractiveLLM(),
            "Offline extractive answers (tests and demos)",
        ),
    ]


def default_parsers() -> list[DocumentParser]:
    parsers: list[DocumentParser] = list(basic_parsers())
    try:
        from vlade_rag.ingestion.parsers.docling import DoclingParser
    except ImportError:
        return parsers
    parsers.append(DoclingParser())
    return parsers


@dataclass
class Runtime:
    settings: Settings
    deps: Dependencies
    tenants: TenantDirectory
    registry: Registry
    closers: list[Closer] = field(default_factory=list)
    checks: dict[str, Callable[[], Awaitable[Any]]] = field(default_factory=dict)

    async def aclose(self) -> None:
        while self.closers:
            await self.closers.pop()()

    async def check(self) -> list[str]:
        """Run the readiness checks. Returns the names of the failed checks."""
        failed = []
        for name, probe in self.checks.items():
            try:
                await probe()
            except Exception:  # any failure means "not ready"
                failed.append(name)
        return failed


def _resolver(registry: Registry, kind: Any, clients: ProviderClients) -> Callable[[Any], Any]:
    cache: dict[str, Any] = {}

    def resolve(cfg: Any) -> Any:
        key = cfg.model_dump_json()
        if key not in cache:
            cache[key] = registry.create(kind, cfg.provider, cfg, clients)
        return cache[key]

    return resolve


async def build_runtime(
    settings: Settings | None = None,
    *,
    tracer: Tracer | None = None,
    load_plugins: bool = True,
) -> Runtime:
    settings = settings or get_settings()
    registry = Registry()
    registry.register_all(builtin_plugins())
    if load_plugins:
        registry.load_entry_points()
    clients = ProviderClients(settings)
    closers: list[Closer] = [clients.aclose]
    checks: dict[str, Callable[[], Awaitable[Any]]] = {}
    ports: dict[str, Any]

    if settings.storage.backend == "memory":
        from vlade_rag.knowledge.memory import memory_adapters

        mem = memory_adapters()
        ports = {
            "repository": mem.repository,
            "vector_index": mem.vector_index,
            "lexical_indexes": {"lexical": mem.lexical_index},
            "job_queue": mem.job_queue,
            "audit_log": mem.audit_log,
            "cache": mem.cache,
        }
        tenants: TenantDirectory = mem.tenants
        object_storage: Any = mem.object_storage
    else:
        if settings.database.url is None:
            raise InvalidArgument("VLADE_DATABASE__URL is required for the postgres backend.")
        if settings.security.api_key_pepper is None:
            raise InvalidArgument("VLADE_SECURITY__API_KEY_PEPPER is required.")
        from vlade_rag.knowledge.memory import MemoryCache, MemoryStore
        from vlade_rag.knowledge.postgres import (
            PgVectorIndex,
            PostgresAuditLog,
            PostgresDatabase,
            PostgresJobQueue,
            PostgresKnowledgeRepository,
            PostgresTenantDirectory,
            TsvectorLexicalIndex,
        )

        db = await PostgresDatabase.connect(
            settings.database.url.get_secret_value(),
            min_size=settings.database.pool_min_size,
            max_size=settings.database.pool_max_size,
        )
        closers.append(db.close)
        checks["database"] = lambda: db.fetchval("SELECT 1")
        ports = {
            "repository": PostgresKnowledgeRepository(db),
            "vector_index": PgVectorIndex(db),
            "lexical_indexes": {"lexical": TsvectorLexicalIndex(db)},
            "job_queue": PostgresJobQueue(db),
            "audit_log": PostgresAuditLog(db),
            "cache": MemoryCache(MemoryStore()),  # per process; Valkey arrives in phase 2
        }
        tenants = PostgresTenantDirectory(db, settings.security.api_key_pepper.get_secret_value())
        object_storage = None

    if object_storage is None or settings.object_storage.backend == "filesystem":
        if settings.object_storage.backend == "filesystem":
            from vlade_rag.knowledge.filesystem import FilesystemObjectStorage

            object_storage = FilesystemObjectStorage(settings.object_storage.path)
        else:
            from vlade_rag.knowledge.memory import MemoryObjectStorage, MemoryStore

            object_storage = MemoryObjectStorage(MemoryStore())

    limits = settings.limits
    deps = Dependencies(
        object_storage=object_storage,
        parsers=default_parsers(),
        normalizer=NativeTextNormalizer(),
        chunker=NativeChunker(),
        fusion=RRFFusion(),
        prompts=BuiltinPromptRegistry(),
        embeddings=_resolver(registry, "embeddings", clients),
        llms=_resolver(registry, "llm", clients),
        limits=Limits(
            max_upload_bytes=limits.max_upload_bytes,
            max_query_chars=limits.max_query_chars,
            max_top_k=limits.max_top_k,
            job_max_attempts=limits.job_max_attempts,
            store_query_text=limits.store_query_text,
        ),
        **ports,
    )
    return Runtime(
        settings=settings,
        deps=deps,
        tenants=tenants,
        registry=registry,
        closers=closers,
        checks=checks,
    )
