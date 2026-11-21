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
from vlade_rag.core.domain.kb_config import EmbeddingsConfig, GenerationConfig, RerankConfig
from vlade_rag.core.ports import (
    DocumentParser,
    EmbeddingProvider,
    LLMProvider,
    PromptRegistry,
    QueryTransformer,
    Reranker,
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
from vlade_rag.retrieval.transform import Mode

Closer = Callable[[], Awaitable[None]]

# Built-in OpenAI-compatible providers that have no ``/rerank`` endpoint (ADR-0018). OpenRouter
# and the providers a user adds under ``VLADE_PROVIDERS__COMPATIBLE__*`` do get a reranker.
NO_RERANK_API = frozenset({"openai", "opencode", "gemini"})


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
        elif provider in p.openai_compatible():
            cfg = p.openai_compatible()[provider]
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


def builtin_plugins(
    compatible: tuple[str, ...] = ("openai", "openrouter", "opencode", "gemini"),
) -> list[PluginSpec]:
    """Built-in adapters. ``compatible`` lists the OpenAI-compatible provider names."""

    def ollama_embeddings(cfg: EmbeddingsConfig, clients: ProviderClients) -> EmbeddingProvider:
        from vlade_rag.generation.providers.ollama import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider(clients.get("ollama"), cfg.model, cfg.dimension)

    def openai_embeddings(provider: str) -> Callable[..., EmbeddingProvider]:
        def factory(cfg: EmbeddingsConfig, clients: ProviderClients) -> EmbeddingProvider:
            from vlade_rag.generation.providers.openai_compatible import (
                OpenAICompatibleEmbeddingProvider,
            )

            send_dimensions = clients.settings.providers.openai_compatible()[
                provider
            ].embedding_dimensions
            return OpenAICompatibleEmbeddingProvider(
                clients.get(provider),
                provider,
                cfg.model,
                cfg.dimension,
                send_dimensions=send_dimensions,
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

    specs = [
        PluginSpec("embeddings", "ollama", ollama_embeddings, "Ollama /api/embed"),
        PluginSpec(
            "embeddings",
            "hashing",
            lambda cfg, clients: HashingEmbeddingProvider(cfg.model, cfg.dimension),
            "Offline feature hashing (tests and demos)",
        ),
        PluginSpec("llm", "ollama", ollama_llm, "Ollama /api/chat"),
        PluginSpec(
            "llm",
            "extractive",
            lambda cfg, clients: ExtractiveLLM(),
            "Offline extractive answers (tests and demos)",
        ),
    ]

    def api_reranker(provider: str) -> Callable[..., Reranker]:
        def factory(cfg: RerankConfig, clients: ProviderClients) -> Reranker:
            from vlade_rag.reranking.api import ApiReranker

            return ApiReranker(clients.get(provider), provider, cfg.model)

        return factory

    def local_reranker(cfg: RerankConfig, clients: ProviderClients) -> Reranker:
        from vlade_rag.reranking.local import SentenceTransformersReranker

        local = clients.settings.providers.local_models
        return SentenceTransformersReranker(
            cfg.model,
            device=local.device,
            batch_size=local.batch_size,
            max_length=local.max_length,
        )

    def llm_transformer(mode: Mode) -> Callable[..., QueryTransformer]:
        # A query transformer plugin gets the same arguments: the LLM resolver, the prompt
        # registry and the longest query the server accepts.
        def factory(
            llms: Callable[[GenerationConfig], LLMProvider],
            prompts: PromptRegistry,
            max_query_chars: int,
        ) -> QueryTransformer:
            from vlade_rag.retrieval.transform import LLMQueryTransformer

            return LLMQueryTransformer(mode, llms, prompts, max_query_chars=max_query_chars)

        return factory

    modes: tuple[Mode, ...] = ("rewrite", "multi_query", "hyde")
    for mode in modes:
        specs.append(PluginSpec("query_transformer", mode, llm_transformer(mode), f"LLM: {mode}"))

    specs.append(
        PluginSpec(
            "reranker",
            "sentence-transformers",
            local_reranker,
            "Local cross-encoder (extra local-models)",
        )
    )

    for name in compatible:
        specs.append(
            PluginSpec("embeddings", name, openai_embeddings(name), f"{name} (OpenAI-compatible)")
        )
        specs.append(PluginSpec("llm", name, openai_llm(name), f"{name} (OpenAI-compatible)"))
        if name not in NO_RERANK_API:
            specs.append(PluginSpec("reranker", name, api_reranker(name), f"{name} (POST /rerank)"))
    return specs


def default_parsers() -> list[DocumentParser]:
    parsers: list[DocumentParser] = list(basic_parsers())
    import importlib.util

    if importlib.util.find_spec("docling") is None:
        return parsers
    from vlade_rag.ingestion.parsers.docling import DoclingParser

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
    compatible = tuple(settings.providers.openai_compatible())
    registry.register_all(builtin_plugins(compatible))
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
            "lexical_indexes": {
                "lexical": mem.lexical_index,
                "fuzzy": mem.fuzzy_index,
                "bm25": mem.lexical_index,  # the memory index already scores with BM25
            },
            "job_queue": mem.job_queue,
            "audit_log": mem.audit_log,
            "cache": mem.cache,
            "rate_limiter": mem.rate_limiter,
        }
        tenants: TenantDirectory = mem.tenants
        object_storage: Any = mem.object_storage
    else:
        if settings.database.url is None:
            raise InvalidArgument("VLADE_DATABASE__URL is required for the postgres backend.")
        if settings.security.api_key_pepper is None:
            raise InvalidArgument("VLADE_SECURITY__API_KEY_PEPPER is required.")
        from vlade_rag.knowledge.memory import MemoryCache, MemoryRateLimiter, MemoryStore
        from vlade_rag.knowledge.postgres import (
            PgSearchLexicalIndex,
            PgVectorIndex,
            PostgresAuditLog,
            PostgresDatabase,
            PostgresJobQueue,
            PostgresKnowledgeRepository,
            PostgresTenantDirectory,
            TrigramLexicalIndex,
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
            "lexical_indexes": {
                "lexical": TsvectorLexicalIndex(db),
                "fuzzy": TrigramLexicalIndex(db),
                "bm25": PgSearchLexicalIndex(db),  # needs the image vlade-postgres-bm25
            },
            "job_queue": PostgresJobQueue(db),
            "audit_log": PostgresAuditLog(db),
            "cache": MemoryCache(MemoryStore()),  # per process unless VLADE_CACHE__URL is set
            "rate_limiter": MemoryRateLimiter(),
        }
        tenants = PostgresTenantDirectory(db, settings.security.api_key_pepper.get_secret_value())
        object_storage = None

    storage_backend = settings.object_storage.backend
    if storage_backend == "s3":
        s3 = settings.object_storage.s3
        if not s3.bucket:
            raise InvalidArgument(
                "VLADE_OBJECT_STORAGE__S3__BUCKET is required for the s3 backend."
            )
        try:
            from vlade_rag.knowledge.s3 import S3ObjectStorage
        except ImportError as exc:
            raise InvalidArgument(
                'The s3 backend needs the "s3" extra: pip install "vlade-rag[s3]"'
            ) from exc
        s3_storage = S3ObjectStorage.from_settings(s3)
        if s3.create_bucket:
            await s3_storage.ensure_bucket()
        checks["object_storage"] = s3_storage.ping
        object_storage = s3_storage
    elif storage_backend == "filesystem":
        from vlade_rag.knowledge.filesystem import FilesystemObjectStorage

        object_storage = FilesystemObjectStorage(settings.object_storage.path)
    elif object_storage is None:
        from vlade_rag.knowledge.memory import MemoryObjectStorage, MemoryStore

        object_storage = MemoryObjectStorage(MemoryStore())

    if settings.cache.url is not None:
        try:
            from vlade_rag.knowledge.valkey import ValkeyCache, ValkeyRateLimiter, connect
        except ImportError as exc:
            raise InvalidArgument(
                'VLADE_CACHE__URL needs the "cache" extra: pip install "vlade-rag[cache]"'
            ) from exc
        client = connect(settings.cache.url.get_secret_value())
        closers.append(client.aclose)
        checks["cache"] = client.ping
        ports["cache"] = ValkeyCache(client)
        ports["rate_limiter"] = ValkeyRateLimiter(client)

    limits = settings.limits
    prompts = BuiltinPromptRegistry()
    llms = _resolver(registry, "llm", clients)
    query_transformers = {
        name: registry.create("query_transformer", name, llms, prompts, limits.max_query_chars)
        for name in registry.names("query_transformer")
    }
    deps = Dependencies(
        object_storage=object_storage,
        parsers=default_parsers(),
        normalizer=NativeTextNormalizer(),
        chunker=NativeChunker(),
        fusion=RRFFusion(),
        prompts=prompts,
        embeddings=_resolver(registry, "embeddings", clients),
        llms=llms,
        rerankers=_resolver(registry, "reranker", clients),
        query_transformers=query_transformers,
        limits=Limits(
            max_upload_bytes=limits.max_upload_bytes,
            max_query_chars=limits.max_query_chars,
            max_top_k=limits.max_top_k,
            rate_per_key_per_minute=limits.rate_per_key_per_minute,
            rate_per_tenant_per_minute=limits.rate_per_tenant_per_minute,
            job_max_attempts=limits.job_max_attempts,
            store_query_text=limits.store_query_text,
        ),
        default_kb_config=settings.default_kb_config,
        tenants=tenants,
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
