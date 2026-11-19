"""Dependencies injected into the use cases."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

from vlade_rag.core.domain.kb_config import EmbeddingsConfig, GenerationConfig, RerankConfig
from vlade_rag.core.ports import (
    AttrValue,
    AuditLog,
    Cache,
    Chunker,
    DocumentParser,
    EmbeddingProvider,
    FusionStrategy,
    JobQueue,
    KnowledgeRepository,
    LexicalIndex,
    LLMProvider,
    ObjectStorage,
    PromptRegistry,
    Reranker,
    Span,
    TextNormalizer,
    Tracer,
    VectorIndex,
)


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


@dataclass(frozen=True, slots=True)
class Limits:
    max_upload_bytes: int = 50 * 1024 * 1024
    max_query_chars: int = 4000
    max_top_k: int = 50
    job_max_attempts: int = 3
    store_query_text: bool = False


@dataclass
class Dependencies:
    """Everything the use cases need. Built by ``vlade_rag.core.registry``."""

    repository: KnowledgeRepository
    vector_index: VectorIndex
    lexical_indexes: Mapping[str, LexicalIndex]  # retriever name -> index ("lexical", "fuzzy")
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
    cache: Cache | None = None
    tracer: Tracer = field(default_factory=NoopTracer)
    limits: Limits = field(default_factory=Limits)

    def parser_for(self, mime_type: str) -> DocumentParser | None:
        for parser in self.parsers:
            if mime_type in parser.mime_types:
                return parser
        return None

    @property
    def supported_mime_types(self) -> frozenset[str]:
        return frozenset(m for p in self.parsers for m in p.mime_types)
