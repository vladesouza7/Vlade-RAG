"""Abstract interfaces implemented by adapters (docs/ARCHITECTURE.md section 5).

Rules:
- Every I/O method is ``async``.
- Every method that reads or writes customer data receives a ``TenantContext``.
- ``ObjectStorage`` and ``Cache`` adapters prefix every key with ``{tenant_id}/`` themselves.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from vlade_rag.core.domain import (
    AuditEvent,
    Chunk,
    ChunkDraft,
    ChunkHit,
    DeletionReport,
    Document,
    DocumentVersion,
    EmbeddingSpace,
    Generation,
    GenerationDelta,
    GenerationParams,
    IngestionJob,
    IngestionStep,
    JobKind,
    KnowledgeBase,
    KnowledgeBaseConfig,
    Message,
    Metadata,
    MetadataFilter,
    ParsedDocument,
    Query,
    RawDocument,
    Role,
    ScoredChunk,
    SourceItem,
    Tenant,
    TenantContext,
)

AttrValue = str | int | float | bool

# ---------------------------------------------------------------- ingestion


@runtime_checkable
class DocumentSource(Protocol):
    name: str

    def list_items(self, ctx: TenantContext, cursor: str | None) -> AsyncIterator[SourceItem]: ...
    async def fetch(self, ctx: TenantContext, item: SourceItem) -> RawDocument: ...


@runtime_checkable
class DocumentParser(Protocol):
    mime_types: frozenset[str]

    async def parse(self, raw: RawDocument) -> ParsedDocument: ...


@runtime_checkable
class TextNormalizer(Protocol):
    def normalize(self, text: str) -> str: ...


@dataclass(frozen=True, slots=True)
class ChunkingParams:
    strategy: Literal["tokens", "recursive", "markdown", "sentence"]
    max_tokens: int
    overlap_tokens: int


@runtime_checkable
class Chunker(Protocol):
    name: str

    def split(self, document: ParsedDocument, params: ChunkingParams) -> list[ChunkDraft]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    provider: str
    model: str
    dimension: int
    max_batch_size: int

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


# ---------------------------------------------------------------- knowledge


@runtime_checkable
class KnowledgeRepository(Protocol):
    # knowledge bases and embedding spaces
    async def create_knowledge_base(
        self, ctx: TenantContext, *, slug: str, name: str, config: KnowledgeBaseConfig
    ) -> KnowledgeBase: ...
    async def get_knowledge_base(self, ctx: TenantContext, slug: str) -> KnowledgeBase: ...
    async def get_knowledge_base_by_id(self, ctx: TenantContext, kb_id: UUID) -> KnowledgeBase: ...
    async def list_knowledge_bases(self, ctx: TenantContext) -> list[KnowledgeBase]: ...
    async def count_documents(self, ctx: TenantContext, kb_id: UUID) -> int: ...
    async def get_embedding_space(self, ctx: TenantContext, space_id: UUID) -> EmbeddingSpace: ...

    # documents and versions
    async def upsert_document(
        self,
        ctx: TenantContext,
        *,
        knowledge_base_id: UUID,
        title: str,
        mime_type: str,
        source_type: str,
        external_id: str | None,
        source_uri: str | None,
        metadata: Metadata,
    ) -> Document: ...
    async def get_document(self, ctx: TenantContext, document_id: UUID) -> Document: ...
    async def create_version(
        self,
        ctx: TenantContext,
        *,
        document_id: UUID,
        content_hash: str,
        storage_key: str,
        size_bytes: int,
    ) -> DocumentVersion: ...
    async def get_current_version(
        self, ctx: TenantContext, document_id: UUID
    ) -> DocumentVersion | None: ...
    async def mark_version_failed(self, ctx: TenantContext, version_id: UUID) -> None: ...

    # chunks
    async def save_chunks(
        self,
        ctx: TenantContext,
        version: DocumentVersion,
        drafts: Sequence[ChunkDraft],
        *,
        language: str,
    ) -> list[Chunk]: ...
    async def get_chunks(self, ctx: TenantContext, chunk_ids: Sequence[UUID]) -> list[Chunk]: ...
    async def list_chunks(self, ctx: TenantContext, version_id: UUID) -> list[Chunk]: ...

    # publication and deletion
    async def publish_version(self, ctx: TenantContext, version_id: UUID) -> None:
        """Atomically make the version visible, hide the previous one and bump the KB epoch."""
        ...

    async def delete_document(
        self, ctx: TenantContext, document_id: UUID, *, dry_run: bool
    ) -> tuple[DeletionReport, list[str]]:
        """Delete (or preview) a document. Returns the report and the object storage keys."""
        ...


@runtime_checkable
class VectorIndex(Protocol):
    async def ensure_space(self, ctx: TenantContext, space: EmbeddingSpace) -> None: ...
    async def upsert(
        self,
        ctx: TenantContext,
        space: EmbeddingSpace,
        knowledge_base_id: UUID,
        items: Sequence[tuple[UUID, Sequence[float]]],
    ) -> None: ...
    async def search(
        self,
        ctx: TenantContext,
        space: EmbeddingSpace,
        knowledge_base_id: UUID,
        vector: Sequence[float],
        top_k: int,
        filters: MetadataFilter | None,
        *,
        ef_search: int = 100,
    ) -> list[ChunkHit]: ...
    async def count(
        self, ctx: TenantContext, space: EmbeddingSpace, chunk_ids: Sequence[UUID]
    ) -> int:
        """Number of the given chunks that have a vector in the space."""
        ...


@runtime_checkable
class LexicalIndex(Protocol):
    name: str  # "tsvector", "pg_search", "trigram"

    async def search(
        self,
        ctx: TenantContext,
        knowledge_base_id: UUID,
        text: str,
        top_k: int,
        filters: MetadataFilter | None,
        language: str,
    ) -> list[ChunkHit]: ...


# ---------------------------------------------------------------- retrieval and generation


@runtime_checkable
class Retriever(Protocol):
    name: str

    async def retrieve(
        self, ctx: TenantContext, kb: KnowledgeBase, query: Query, top_k: int
    ) -> list[ScoredChunk]: ...


@runtime_checkable
class FusionStrategy(Protocol):
    name: str

    def fuse(
        self, results: Mapping[str, Sequence[ScoredChunk]], top_k: int
    ) -> list[ScoredChunk]: ...


@runtime_checkable
class Reranker(Protocol):
    name: str

    async def rerank(
        self, query: str, candidates: Sequence[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]: ...


@runtime_checkable
class QueryTransformer(Protocol):
    name: str

    async def transform(self, ctx: TenantContext, query: Query) -> list[Query]: ...


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def generate(
        self, messages: Sequence[Message], params: GenerationParams
    ) -> Generation: ...
    def stream(
        self, messages: Sequence[Message], params: GenerationParams
    ) -> AsyncIterator[GenerationDelta]: ...


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    name: str
    version: str
    language: str
    system: str
    user: str
    not_found_answer: str

    def render_user(self, **values: str) -> str:
        return self.user.format(**values)


@runtime_checkable
class PromptRegistry(Protocol):
    async def get(self, name: str, language: str, version: str | None = None) -> PromptTemplate: ...


# ---------------------------------------------------------------- storage and cache


@runtime_checkable
class ObjectStorage(Protocol):
    async def put(self, ctx: TenantContext, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, ctx: TenantContext, key: str) -> bytes: ...
    async def delete(self, ctx: TenantContext, key: str) -> None: ...
    async def delete_prefix(self, ctx: TenantContext, prefix: str) -> int: ...


@runtime_checkable
class Cache(Protocol):
    async def get(self, ctx: TenantContext, key: str) -> bytes | None: ...
    async def set(self, ctx: TenantContext, key: str, value: bytes, ttl_seconds: int) -> None: ...
    async def delete_prefix(self, ctx: TenantContext, prefix: str) -> int: ...


# ---------------------------------------------------------------- jobs, audit, tenants


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job: IngestionJob
    ctx: TenantContext


@runtime_checkable
class JobQueue(Protocol):
    async def enqueue(
        self,
        ctx: TenantContext,
        *,
        kind: JobKind,
        knowledge_base_id: UUID | None,
        input: Metadata,
    ) -> IngestionJob: ...
    async def get(self, ctx: TenantContext, job_id: UUID) -> IngestionJob: ...
    async def claim(self, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        """Take the oldest pending job of any tenant. Returns the job and a worker context."""
        ...

    async def heartbeat(self, job_id: UUID, worker_id: str, lease_seconds: int) -> None: ...
    async def record_step(self, ctx: TenantContext, job_id: UUID, step: IngestionStep) -> None: ...
    async def complete(self, ctx: TenantContext, job_id: UUID, result: Metadata) -> None: ...
    async def fail(
        self, ctx: TenantContext, job_id: UUID, error: Metadata, *, retry: bool, max_attempts: int
    ) -> None: ...
    async def requeue_expired(self, max_attempts: int) -> int: ...


@runtime_checkable
class AuditLog(Protocol):
    async def record(self, ctx: TenantContext, event: AuditEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class IssuedApiKey:
    key: str  # shown once; never stored
    key_prefix: str
    principal_id: UUID
    roles: frozenset[Role]


@runtime_checkable
class TenantDirectory(Protocol):
    async def create_tenant(self, slug: str, name: str) -> Tenant: ...
    async def get_tenant(self, slug: str) -> Tenant: ...
    async def issue_api_key(
        self, tenant_id: UUID, *, principal_name: str, roles: frozenset[Role]
    ) -> IssuedApiKey: ...
    async def authenticate(self, api_key: str, *, interface: str) -> TenantContext:
        """Raise ``Unauthenticated`` for unknown, revoked or expired keys."""
        ...


# ---------------------------------------------------------------- evaluation and tracing


@dataclass(frozen=True, slots=True)
class EvalItem:
    question: str
    expected_answer: str | None = None
    relevant_chunk_ids: tuple[UUID, ...] = ()
    relevant_document_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class EvalReport:
    metrics: Mapping[str, float]
    config: Mapping[str, object]
    items: int
    details: Sequence[Mapping[str, object]] = field(default_factory=tuple)


@runtime_checkable
class Evaluator(Protocol):
    name: str

    async def evaluate(
        self, ctx: TenantContext, kb: KnowledgeBase, items: Sequence[EvalItem], k: int
    ) -> EvalReport: ...


@runtime_checkable
class Span(Protocol):
    def set_attribute(self, key: str, value: AttrValue) -> None: ...
    def add_event(self, name: str, attributes: Mapping[str, AttrValue] | None = None) -> None: ...


@runtime_checkable
class Tracer(Protocol):
    def span(
        self, name: str, attributes: Mapping[str, AttrValue] | None = None
    ) -> AbstractContextManager[Span]: ...
    def current_trace_id(self) -> str | None: ...


__all__ = [
    "AttrValue",
    "AuditLog",
    "Cache",
    "Chunker",
    "ChunkingParams",
    "ClaimedJob",
    "DocumentParser",
    "DocumentSource",
    "EmbeddingProvider",
    "EvalItem",
    "EvalReport",
    "Evaluator",
    "FusionStrategy",
    "IssuedApiKey",
    "JobQueue",
    "KnowledgeRepository",
    "LLMProvider",
    "LexicalIndex",
    "ObjectStorage",
    "PromptRegistry",
    "PromptTemplate",
    "QueryTransformer",
    "Reranker",
    "Retriever",
    "Span",
    "TenantDirectory",
    "TextNormalizer",
    "Tracer",
    "VectorIndex",
]
