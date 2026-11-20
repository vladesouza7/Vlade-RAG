"""Entities (docs/ARCHITECTURE.md section 4.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from vlade_rag.core.domain.kb_config import KnowledgeBaseConfig

JsonValue = Any  # JSON-compatible value; precise recursive typing adds no safety here.
Metadata = Mapping[str, JsonValue]


class Distance(StrEnum):
    COSINE = "cosine"
    DOT = "dot"
    L2 = "l2"


class SpaceStatus(StrEnum):
    BUILDING = "building"
    ACTIVE = "active"
    RETIRED = "retired"


class VersionStatus(StrEnum):
    INDEXING = "indexing"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class JobKind(StrEnum):
    INGEST = "ingest"
    REINDEX = "reindex"
    EVALUATION = "evaluation"
    SYNC = "sync"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_final(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


@dataclass(frozen=True, slots=True)
class Tenant:
    id: UUID
    slug: str
    name: str
    settings: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmbeddingSpace:
    id: UUID
    tenant_id: UUID
    provider: str
    model: str
    dimension: int
    version: int
    distance: Distance = Distance.COSINE
    status: SpaceStatus = SpaceStatus.ACTIVE

    def same_vectors_as(self, other: EmbeddingSpace) -> bool:
        """True when vectors of both spaces are comparable."""
        return (self.provider, self.model, self.dimension, self.distance) == (
            other.provider,
            other.model,
            other.dimension,
            other.distance,
        )


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    id: UUID
    tenant_id: UUID
    slug: str
    name: str
    config: KnowledgeBaseConfig
    active_embedding_space_id: UUID
    epoch: int = 0

    @property
    def language(self) -> str:
        return self.config.language


@dataclass(frozen=True, slots=True)
class Document:
    id: UUID
    tenant_id: UUID
    knowledge_base_id: UUID
    title: str
    mime_type: str
    source_type: str
    external_id: str | None = None
    source_uri: str | None = None
    current_version_id: UUID | None = None
    metadata: Metadata = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    id: UUID
    tenant_id: UUID
    document_id: UUID
    version: int
    content_hash: str
    storage_key: str
    size_bytes: int
    status: VersionStatus = VersionStatus.INDEXING


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    """A chunk before it receives identifiers. Offsets index the normalized document text."""

    ordinal: int
    text: str
    token_count: int
    start_offset: int
    end_offset: int
    page: int | None = None
    section: str | None = None
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Chunk:
    id: UUID
    tenant_id: UUID
    knowledge_base_id: UUID
    document_id: UUID
    document_version_id: UUID
    ordinal: int
    text: str
    token_count: int
    start_offset: int
    end_offset: int
    page: int | None = None
    section: str | None = None
    metadata: Metadata = field(default_factory=dict)
    document_title: str = ""


@dataclass(frozen=True, slots=True)
class ChunkHit:
    """Index result before the chunk is loaded."""

    chunk_id: UUID
    score: float


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    chunk: Chunk
    score: float
    rank: int  # starts at 1
    retriever: str  # "dense", "lexical", "fuzzy", "bm25", "fusion", "rerank"


@dataclass(frozen=True, slots=True)
class IngestionStep:
    name: str
    status: JobStatus
    attempt: int = 1
    document_id: UUID | None = None
    error: Metadata | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class IngestionJob:
    id: UUID
    tenant_id: UUID
    kind: JobKind
    status: JobStatus
    input: Metadata
    knowledge_base_id: UUID | None = None
    requested_by: UUID | None = None
    result: Metadata | None = None
    error: Metadata | None = None
    attempt: int = 0
    steps: tuple[IngestionStep, ...] = ()
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DeletionReport:
    document_id: UUID
    versions: int
    chunks: int
    embeddings: int
    stored_objects: int
    executed: bool


@dataclass(frozen=True, slots=True)
class AuditEvent:
    tenant_id: UUID
    interface: str
    action: str
    outcome: str  # success, denied, error, preview
    principal_id: UUID | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    details: Metadata = field(default_factory=dict)
    trace_id: str | None = None
    created_at: datetime | None = None  # set by the audit log when it stores the event


@dataclass(frozen=True, slots=True)
class QueryLogEntry:
    """One search or query. Stores the hash of the query text by default (RF-42)."""

    interface: str
    mode: str  # search, query
    query_hash: bytes
    result_count: int
    latency_ms: int
    knowledge_base_id: UUID | None = None
    principal_id: UUID | None = None
    query_text: str | None = None
    grounded: bool | None = None
    trace_id: str | None = None
