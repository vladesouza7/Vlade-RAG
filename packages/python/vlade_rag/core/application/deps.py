"""Dependencies injected into the use cases."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vlade_rag.core.application.semantic_cache import SemanticCache, SemanticCacheSettings
from vlade_rag.core.domain.kb_config import EmbeddingsConfig, GenerationConfig, RerankConfig
from vlade_rag.core.ports import (
    AttrValue,
    AuditLog,
    Cache,
    Chunker,
    DocumentParser,
    DocumentSource,
    EmbeddingProvider,
    EvaluationDatasets,
    EvaluationRunner,
    FusionStrategy,
    GraphIndex,
    JobQueue,
    KnowledgeRepository,
    LexicalIndex,
    LLMProvider,
    Metrics,
    ObjectStorage,
    PromptRegistry,
    QueryTransformer,
    RateLimiter,
    Reranker,
    Span,
    TenantDirectory,
    TextNormalizer,
    Tracer,
    VectorIndex,
    WikiPageCodec,
    WikiStore,
)

if TYPE_CHECKING:
    from vlade_rag.core.application.answer import AnswerEngine


class _NoopSpan:
    def set_attribute(self, key: str, value: AttrValue) -> None:
        return None

    def add_event(self, name: str, attributes: Mapping[str, AttrValue] | None = None) -> None:
        return None


class NoopTracer:
    @contextmanager
    def span(self, name: str, attributes: Mapping[str, AttrValue] | None = None) -> Iterator[Span]:
        yield _NoopSpan()

    def current_trace_id(self) -> str | None:
        return None


class NoopMetrics:
    def counter(
        self, name: str, value: float = 1, attributes: Mapping[str, AttrValue] | None = None
    ) -> None:
        return None

    def histogram(
        self, name: str, value: float, attributes: Mapping[str, AttrValue] | None = None
    ) -> None:
        return None

    def gauge(
        self, name: str, value: float, attributes: Mapping[str, AttrValue] | None = None
    ) -> None:
        return None

    def llm_usage(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
        return None


@dataclass(frozen=True, slots=True)
class Limits:
    max_upload_bytes: int = 50 * 1024 * 1024
    max_query_chars: int = 4000
    max_top_k: int = 50
    rate_per_key_per_minute: int = 0  # 0: no limit
    rate_per_tenant_per_minute: int = 0
    job_max_attempts: int = 3
    store_query_text: bool = False


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    """Rules for a document downloaded from an origin URI (ARCHITECTURE section 15)."""

    allowed_domains: tuple[str, ...] = ()
    max_bytes: int = 50 * 1024 * 1024
    timeout: float = 30.0


@dataclass
class Dependencies:
    """Everything the use cases need. Built by ``vlade_rag.core.registry``."""

    repository: KnowledgeRepository
    vector_index: VectorIndex
    # retriever name -> index ("lexical", "fuzzy", "bm25")
    lexical_indexes: Mapping[str, LexicalIndex]
    object_storage: ObjectStorage
    job_queue: JobQueue
    audit_log: AuditLog
    parsers: Sequence[DocumentParser]
    normalizer: TextNormalizer
    chunker: Chunker
    fusion: FusionStrategy
    prompts: PromptRegistry
    embeddings: Callable[[EmbeddingsConfig], EmbeddingProvider]
    llms: Callable[[GenerationConfig], LLMProvider]
    rerankers: Callable[[RerankConfig], Reranker] | None = None
    # ``retrieval.query_transform`` value -> transformer ("rewrite", "multi_query", "hyde").
    query_transformers: Mapping[str, QueryTransformer] = field(default_factory=dict)
    # ``orchestration.engine`` value -> engine. Without "pipeline", the built-in one runs.
    answer_engines: Mapping[str, AnswerEngine] = field(default_factory=dict)
    cache: Cache | None = None
    semantic_cache: SemanticCache = field(
        default_factory=lambda: SemanticCache(None, SemanticCacheSettings())
    )
    rate_limiter: RateLimiter | None = None  # without it no request limit applies
    tenants: TenantDirectory | None = None  # needed for quotas; without it no quota applies
    tracer: Tracer = field(default_factory=NoopTracer)
    metrics: Metrics = field(default_factory=NoopMetrics)
    limits: Limits = field(default_factory=Limits)
    sources: SourcePolicy = field(default_factory=SourcePolicy)
    # Connectors of task 5.2, keyed by name. Empty by default: no source is active.
    document_sources: Mapping[str, DocumentSource] = field(default_factory=dict)
    # Evaluation needs the registry of datasets and a worker runner. Both are wired in bootstrap.
    evaluation_datasets: EvaluationDatasets | None = None
    evaluation_runner: EvaluationRunner | None = None
    default_kb_config: Mapping[str, Any] = field(default_factory=dict)
    # Knowledge graph (phase 6). None: no base of this server can enable the graph.
    graph_index: GraphIndex | None = None
    # LLM-Wiki store (task 6.12). None: no wiki tool is available.
    wiki_store: WikiStore | None = None
    wiki_codec: WikiPageCodec | None = None

    def parser_for(self, mime_type: str) -> DocumentParser | None:
        for parser in self.parsers:
            if mime_type in parser.mime_types:
                return parser
        return None

    @property
    def supported_mime_types(self) -> frozenset[str]:
        return frozenset(m for p in self.parsers for m in p.mime_types)
