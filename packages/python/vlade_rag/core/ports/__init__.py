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
from datetime import datetime
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
    QueryLogEntry,
    RawDocument,
    Role,
    ScoredChunk,
    SourceItem,
    Tenant,
    TenantContext,
    TenantQuotas,
    TenantUsage,
)
from vlade_rag.core.domain.kb_config import EmbeddingsConfig

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


@dataclass(frozen=True, slots=True)
class SpaceMaintenanceInfo:
    """An embedding space with the dates the maintenance module needs."""

    space: EmbeddingSpace
    created_at: datetime
    retired_at: datetime | None


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
    async def get_usage(self, ctx: TenantContext) -> TenantUsage:
        """Documents of the tenant and bytes of its versions in ``indexing`` or ``published``."""
        ...

    async def get_embedding_space(self, ctx: TenantContext, space_id: UUID) -> EmbeddingSpace: ...

    # maintenance (roadmap 4.4)
    async def list_spaces_for_maintenance(self, ctx: TenantContext) -> list[SpaceMaintenanceInfo]:
        """Every space of the tenant with its creation and retirement dates."""
        ...

    async def delete_embedding_space(self, ctx: TenantContext, space_id: UUID) -> bool:
        """Delete a retired or building space with its vectors. Never delete an active one.
        Returns ``True`` when a space was deleted."""
        ...

    async def count_superseded_versions(self, ctx: TenantContext, older_than: datetime) -> int:
        """Number of superseded versions created before ``older_than``."""
        ...

    async def delete_superseded_versions(self, ctx: TenantContext, older_than: datetime) -> int:
        """Delete superseded versions created before ``older_than`` and their chunks/vectors."""
        ...

    # reindex (ARCHITECTURE section 13, ADR-0027)
    async def create_embedding_space(
        self, ctx: TenantContext, embeddings: EmbeddingsConfig
    ) -> EmbeddingSpace:
        """A new space with status ``building``. No base uses it until it is activated."""
        ...

    async def list_published_chunks(
        self, ctx: TenantContext, kb_id: UUID, *, after: UUID | None, limit: int
    ) -> list[Chunk]:
        """Published chunks of the base in id order, the first ``limit`` after ``after``."""
        ...

    async def list_chunks_without_vector(
        self, ctx: TenantContext, kb_id: UUID, space_id: UUID, *, limit: int
    ) -> list[Chunk]:
        """Published chunks of the base that have no vector in the space."""
        ...

    async def activate_embedding_space(
        self, ctx: TenantContext, kb_id: UUID, space_id: UUID, embeddings: EmbeddingsConfig
    ) -> UUID:
        """In one transaction: make the space active for the base, retire the old one, store
        ``embeddings`` in the configuration and bump the epoch. Returns the old space id.

        Raises ``MissingVectors`` when a published chunk has no vector in the space. The check
        and the switch hold the lock of the base, which ``publish_version`` also takes."""
        ...

    async def update_knowledge_base_config(
        self, ctx: TenantContext, kb_id: UUID, config: KnowledgeBaseConfig
    ) -> KnowledgeBase: ...
    async def list_current_versions(
        self, ctx: TenantContext, kb_id: UUID
    ) -> list[tuple[Document, DocumentVersion]]:
        """Every document of the base that has a published version, with that version."""
        ...

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
    async def find_document(
        self, ctx: TenantContext, *, knowledge_base_id: UUID, external_id: str
    ) -> Document | None:
        """The document of the base with this external id, or ``None``."""
        ...

    async def create_version(
        self,
        ctx: TenantContext,
        *,
        document_id: UUID,
        content_hash: str,
        storage_key: str,
        size_bytes: int,
    ) -> DocumentVersion: ...
    async def get_version(self, ctx: TenantContext, version_id: UUID) -> DocumentVersion: ...
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
    async def published_chunks(
        self, ctx: TenantContext, kb_id: UUID, chunk_ids: Sequence[UUID]
    ) -> Mapping[UUID, Metadata]:
        """Metadata of the published chunks of a base, keyed by chunk id.

        Vector stores without a relational join use this to apply publication and metadata
        filters at query time.
        """
        ...

    async def list_chunks(self, ctx: TenantContext, version_id: UUID) -> list[Chunk]: ...

    # publication and deletion
    async def publish_version(
        self,
        ctx: TenantContext,
        version_id: UUID,
        *,
        embedding_space_id: UUID | None = None,
        expected_version_id: UUID | None = None,
    ) -> None:
        """Atomically make the version visible, hide the previous one and bump the KB epoch.

        With ``embedding_space_id``, raise ``EmbeddingSpaceChanged`` when it is no longer the
        active space of the base: the vectors of the version are in an old space. With
        ``expected_version_id``, raise ``VersionChanged`` when another version became current."""
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

    async def drop_space(self, ctx: TenantContext, space: EmbeddingSpace) -> None:
        """Drop the physical index of a deleted space. Without one, do nothing."""
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

    async def transform(self, ctx: TenantContext, kb: KnowledgeBase, query: Query) -> list[Query]:
        """Return the queries to run. The first one is the original query."""
        ...


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


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: float  # 0 when allowed
    remaining: float  # tokens left after this call


@runtime_checkable
class RateLimiter(Protocol):
    """Token buckets and daily counters. Adapters prefix every key with the tenant id."""

    async def take(
        self,
        tenant_id: UUID,
        key: str,
        *,
        capacity: int,
        refill_per_second: float,
        cost: int = 1,
    ) -> RateDecision:
        """Take ``cost`` tokens from the bucket ``key``. A new bucket starts full."""
        ...

    async def count_day(self, tenant_id: UUID, key: str, *, increment: bool) -> int:
        """Requests counted under ``key`` on the current UTC day. ``increment`` adds one first."""
        ...


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
    async def pending_count(self, kind: JobKind) -> int:
        """Number of pending jobs of this kind, across tenants. Feeds the queue-depth gauge."""
        ...

    async def find_active(
        self, ctx: TenantContext, knowledge_base_id: UUID, kind: JobKind
    ) -> IngestionJob | None:
        """The oldest pending or running job of this kind for the base, or ``None``."""
        ...

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
    async def record(self, ctx: TenantContext, event: AuditEvent) -> UUID:
        """Store the event and return its id."""
        ...

    async def record_query(self, ctx: TenantContext, entry: QueryLogEntry) -> None: ...
    async def list_events(
        self,
        ctx: TenantContext,
        *,
        action: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Events of the tenant of ``ctx``, newest first. ``created_at`` is always set."""
        ...


@dataclass(frozen=True, slots=True)
class IssuedApiKey:
    key: str  # shown once; never stored
    key_prefix: str
    principal_id: UUID
    roles: frozenset[Role]


@dataclass(frozen=True, slots=True)
class ApiKeyInfo:
    """A key as listed to an administrator. It never contains the secret."""

    key_prefix: str
    principal_id: UUID
    principal_name: str
    roles: frozenset[Role]
    revoked: bool


@runtime_checkable
class TenantDirectory(Protocol):
    async def create_tenant(self, slug: str, name: str) -> Tenant: ...
    async def get_tenant(self, slug: str) -> Tenant: ...
    async def get_settings(self, tenant_id: UUID) -> Metadata:
        """The ``settings`` object of the tenant (quotas, MCP flags)."""
        ...

    async def set_mcp_write_tools(self, tenant_id: UUID, enabled: bool) -> None:
        """Set ``settings.mcp.write_tools_enabled`` and record ``tenant.mcp_update``."""
        ...

    async def get_quotas(self, tenant_id: UUID) -> TenantQuotas: ...
    async def set_quotas(self, tenant_id: UUID, quotas: TenantQuotas) -> None:
        """Replace the quotas of the tenant and record ``tenant.quota_update``."""
        ...

    async def issue_api_key(
        self, tenant_id: UUID, *, principal_name: str, roles: frozenset[Role]
    ) -> IssuedApiKey:
        """Create the key and record ``api_key.issue``."""
        ...

    async def list_api_keys(self, tenant_id: UUID) -> list[ApiKeyInfo]: ...
    async def revoke_api_key(self, tenant_id: UUID, key_prefix: str) -> None:
        """Revoke the key and record ``api_key.revoke``. Raise ``NotFound`` for another tenant."""
        ...

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
    # Titles of the relevant documents (the file names of a dataset). A document is relevant if
    # its id or its title is listed.
    relevant_document_titles: tuple[str, ...] = ()


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
class EvaluationDatasets(Protocol):
    """Registry of named datasets, addressed by name and never by a caller-supplied path."""

    async def list_names(self) -> tuple[str, ...]: ...
    async def load(self, name: str) -> tuple[EvalItem, ...]: ...


@runtime_checkable
class EvaluationRunner(Protocol):
    """Worker side of an ``evaluation`` job."""

    async def run(self, ctx: TenantContext, job: IngestionJob) -> Metadata: ...


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


@runtime_checkable
class Metrics(Protocol):
    """Application metrics. Never use ``tenant_id`` as a label (ADR-0015)."""

    def counter(
        self, name: str, value: float = 1, attributes: Mapping[str, AttrValue] | None = None
    ) -> None: ...

    def histogram(
        self, name: str, value: float, attributes: Mapping[str, AttrValue] | None = None
    ) -> None: ...

    def gauge(
        self, name: str, value: float, attributes: Mapping[str, AttrValue] | None = None
    ) -> None: ...

    def llm_usage(
        self, provider: str, model: str, input_tokens: int, output_tokens: int
    ) -> None: ...


__all__ = [
    "ApiKeyInfo",
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
    "EvaluationDatasets",
    "EvaluationRunner",
    "Evaluator",
    "FusionStrategy",
    "IssuedApiKey",
    "JobQueue",
    "KnowledgeRepository",
    "LLMProvider",
    "LexicalIndex",
    "Metrics",
    "ObjectStorage",
    "PromptRegistry",
    "PromptTemplate",
    "QueryTransformer",
    "RateDecision",
    "RateLimiter",
    "Reranker",
    "Retriever",
    "SpaceMaintenanceInfo",
    "Span",
    "TenantDirectory",
    "TextNormalizer",
    "Tracer",
    "VectorIndex",
]
