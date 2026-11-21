"""In-memory adapters for tests and prototypes.

All adapters share one ``MemoryStore``. Data is partitioned by tenant, so an id of another
tenant is simply not found. Not thread-safe; use one event loop.
"""

from __future__ import annotations

import math
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from vlade_rag.core.domain import (
    AuditEvent,
    Chunk,
    ChunkDraft,
    ChunkHit,
    Conflict,
    DeletionReport,
    Document,
    DocumentVersion,
    EmbeddingSpace,
    IngestionJob,
    IngestionStep,
    InvalidArgument,
    JobKind,
    JobStatus,
    KnowledgeBase,
    KnowledgeBaseConfig,
    Metadata,
    MetadataFilter,
    NotFound,
    QueryLogEntry,
    Role,
    SpaceStatus,
    Tenant,
    TenantContext,
    TenantQuotas,
    TenantUsage,
    Unauthenticated,
    VersionStatus,
    matches,
    uuid7,
)
from vlade_rag.core.domain.api_keys import generate_api_key, hash_secret, parse_api_key
from vlade_rag.core.ports import ApiKeyInfo, ClaimedJob, IssuedApiKey, RateDecision
from vlade_rag.knowledge.object_keys import validate_object_key
from vlade_rag.native import token_spans


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _TenantData:
    kbs: dict[UUID, KnowledgeBase] = field(default_factory=dict)
    spaces: dict[UUID, EmbeddingSpace] = field(default_factory=dict)
    documents: dict[UUID, Document] = field(default_factory=dict)
    versions: dict[UUID, DocumentVersion] = field(default_factory=dict)
    chunks: dict[UUID, Chunk] = field(default_factory=dict)
    published: set[UUID] = field(default_factory=set)
    vectors: dict[UUID, dict[UUID, list[float]]] = field(default_factory=dict)
    jobs: dict[UUID, IngestionJob] = field(default_factory=dict)
    audit: list[AuditEvent] = field(default_factory=list)
    queries: list[QueryLogEntry] = field(default_factory=list)
    objects: dict[str, bytes] = field(default_factory=dict)
    cache: dict[str, tuple[bytes, float]] = field(default_factory=dict)


@dataclass
class _KeyRecord:
    tenant_id: UUID
    principal_id: UUID
    key_hash: bytes
    roles: frozenset[Role]
    revoked: bool = False
    principal_name: str = ""


@dataclass
class _JobLease:
    worker_id: str
    until: datetime


class MemoryStore:
    def __init__(self, pepper: str = "memory-pepper") -> None:
        self.pepper = pepper
        self.tenants: dict[UUID, Tenant] = {}
        self.keys: dict[str, _KeyRecord] = {}
        self.leases: dict[UUID, _JobLease] = {}
        self._data: dict[UUID, _TenantData] = {}

    def data(self, ctx_or_tenant: TenantContext | UUID) -> _TenantData:
        tenant_id = (
            ctx_or_tenant.tenant_id if isinstance(ctx_or_tenant, TenantContext) else ctx_or_tenant
        )
        return self._data.setdefault(tenant_id, _TenantData())

    def all_data(self) -> list[tuple[UUID, _TenantData]]:
        return list(self._data.items())


# ---------------------------------------------------------------- knowledge repository


class MemoryKnowledgeRepository:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def create_knowledge_base(
        self, ctx: TenantContext, *, slug: str, name: str, config: KnowledgeBaseConfig
    ) -> KnowledgeBase:
        data = self.store.data(ctx)
        if any(kb.slug == slug for kb in data.kbs.values()):
            raise Conflict(f"Knowledge base '{slug}' already exists.")
        emb = config.embeddings
        space = EmbeddingSpace(
            id=uuid7(),
            tenant_id=ctx.tenant_id,
            provider=emb.provider,
            model=emb.model,
            dimension=emb.dimension,
            version=1,
        )
        kb = KnowledgeBase(
            id=uuid7(),
            tenant_id=ctx.tenant_id,
            slug=slug,
            name=name,
            config=config,
            active_embedding_space_id=space.id,
            updated_at=_now(),
        )
        data.spaces[space.id] = space
        data.kbs[kb.id] = kb
        return kb

    async def get_knowledge_base(self, ctx: TenantContext, slug: str) -> KnowledgeBase:
        for kb in self.store.data(ctx).kbs.values():
            if kb.slug == slug:
                return kb
        raise NotFound(f"Knowledge base '{slug}' does not exist.")

    async def get_knowledge_base_by_id(self, ctx: TenantContext, kb_id: UUID) -> KnowledgeBase:
        kb = self.store.data(ctx).kbs.get(kb_id)
        if kb is None:
            raise NotFound("Knowledge base does not exist.")
        return kb

    async def list_knowledge_bases(self, ctx: TenantContext) -> list[KnowledgeBase]:
        return sorted(self.store.data(ctx).kbs.values(), key=lambda kb: kb.slug)

    async def count_documents(self, ctx: TenantContext, kb_id: UUID) -> int:
        docs = self.store.data(ctx).documents.values()
        return sum(1 for d in docs if d.knowledge_base_id == kb_id)

    async def get_usage(self, ctx: TenantContext) -> TenantUsage:
        data = self.store.data(ctx)
        counted = {VersionStatus.INDEXING, VersionStatus.PUBLISHED}
        return TenantUsage(
            documents=len(data.documents),
            bytes=sum(v.size_bytes for v in data.versions.values() if v.status in counted),
        )

    async def get_embedding_space(self, ctx: TenantContext, space_id: UUID) -> EmbeddingSpace:
        space = self.store.data(ctx).spaces.get(space_id)
        if space is None:
            raise NotFound("Embedding space does not exist.")
        return space

    async def find_document(
        self, ctx: TenantContext, *, knowledge_base_id: UUID, external_id: str
    ) -> Document | None:
        for doc in self.store.data(ctx).documents.values():
            if doc.knowledge_base_id == knowledge_base_id and doc.external_id == external_id:
                return doc
        return None

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
    ) -> Document:
        data = self.store.data(ctx)
        await self.get_knowledge_base_by_id(ctx, knowledge_base_id)
        if external_id is not None:
            for doc in data.documents.values():
                if doc.knowledge_base_id == knowledge_base_id and doc.external_id == external_id:
                    updated = replace(
                        doc,
                        title=title,
                        mime_type=mime_type,
                        source_type=source_type,
                        source_uri=source_uri,
                        metadata=dict(metadata),
                        updated_at=_now(),
                    )
                    data.documents[doc.id] = updated
                    return updated
        doc = Document(
            id=uuid7(),
            tenant_id=ctx.tenant_id,
            knowledge_base_id=knowledge_base_id,
            title=title,
            mime_type=mime_type,
            source_type=source_type,
            external_id=external_id,
            source_uri=source_uri,
            metadata=dict(metadata),
            created_at=_now(),
            updated_at=_now(),
        )
        data.documents[doc.id] = doc
        return doc

    async def get_document(self, ctx: TenantContext, document_id: UUID) -> Document:
        doc = self.store.data(ctx).documents.get(document_id)
        if doc is None:
            raise NotFound("Document does not exist.")
        return doc

    async def create_version(
        self,
        ctx: TenantContext,
        *,
        document_id: UUID,
        content_hash: str,
        storage_key: str,
        size_bytes: int,
    ) -> DocumentVersion:
        data = self.store.data(ctx)
        await self.get_document(ctx, document_id)
        number = 1 + max(
            (v.version for v in data.versions.values() if v.document_id == document_id),
            default=0,
        )
        version = DocumentVersion(
            id=uuid7(),
            tenant_id=ctx.tenant_id,
            document_id=document_id,
            version=number,
            content_hash=content_hash,
            storage_key=storage_key,
            size_bytes=size_bytes,
        )
        data.versions[version.id] = version
        return version

    async def get_version(self, ctx: TenantContext, version_id: UUID) -> DocumentVersion:
        version = self.store.data(ctx).versions.get(version_id)
        if version is None:
            raise NotFound("Document version does not exist.")
        return version

    async def get_current_version(
        self, ctx: TenantContext, document_id: UUID
    ) -> DocumentVersion | None:
        doc = await self.get_document(ctx, document_id)
        if doc.current_version_id is None:
            return None
        return self.store.data(ctx).versions.get(doc.current_version_id)

    async def mark_version_failed(self, ctx: TenantContext, version_id: UUID) -> None:
        data = self.store.data(ctx)
        version = data.versions.get(version_id)
        if version is None:
            raise NotFound("Document version does not exist.")
        data.versions[version_id] = replace(version, status=VersionStatus.FAILED)

    async def save_chunks(
        self,
        ctx: TenantContext,
        version: DocumentVersion,
        drafts: Sequence[ChunkDraft],
        *,
        language: str,
    ) -> list[Chunk]:
        data = self.store.data(ctx)
        doc = await self.get_document(ctx, version.document_id)
        for old in [c for c in data.chunks.values() if c.document_version_id == version.id]:
            del data.chunks[old.id]  # idempotent re-run of the step
        saved = []
        for draft in drafts:
            chunk = Chunk(
                id=uuid7(),
                tenant_id=ctx.tenant_id,
                knowledge_base_id=doc.knowledge_base_id,
                document_id=doc.id,
                document_version_id=version.id,
                ordinal=draft.ordinal,
                text=draft.text,
                token_count=draft.token_count,
                start_offset=draft.start_offset,
                end_offset=draft.end_offset,
                page=draft.page,
                section=draft.section,
                metadata={**doc.metadata, **draft.metadata},
                document_title=doc.title,
            )
            data.chunks[chunk.id] = chunk
            saved.append(chunk)
        return saved

    async def get_chunks(self, ctx: TenantContext, chunk_ids: Sequence[UUID]) -> list[Chunk]:
        chunks = self.store.data(ctx).chunks
        return [chunks[cid] for cid in chunk_ids if cid in chunks]

    async def list_chunks(self, ctx: TenantContext, version_id: UUID) -> list[Chunk]:
        chunks = self.store.data(ctx).chunks.values()
        return sorted(
            (c for c in chunks if c.document_version_id == version_id), key=lambda c: c.ordinal
        )

    async def publish_version(self, ctx: TenantContext, version_id: UUID) -> None:
        data = self.store.data(ctx)
        version = data.versions.get(version_id)
        if version is None:
            raise NotFound("Document version does not exist.")
        doc = data.documents[version.document_id]
        if doc.current_version_id and doc.current_version_id != version_id:
            old = data.versions[doc.current_version_id]
            data.versions[old.id] = replace(old, status=VersionStatus.SUPERSEDED)
            for c in data.chunks.values():
                if c.document_version_id == old.id:
                    data.published.discard(c.id)
        for c in data.chunks.values():
            if c.document_version_id == version_id:
                data.published.add(c.id)
        data.versions[version_id] = replace(version, status=VersionStatus.PUBLISHED)
        data.documents[doc.id] = replace(doc, current_version_id=version_id, updated_at=_now())
        kb = data.kbs[doc.knowledge_base_id]
        data.kbs[kb.id] = replace(kb, epoch=kb.epoch + 1, updated_at=_now())

    async def delete_document(
        self, ctx: TenantContext, document_id: UUID, *, dry_run: bool
    ) -> tuple[DeletionReport, list[str]]:
        data = self.store.data(ctx)
        doc = await self.get_document(ctx, document_id)
        versions = [v for v in data.versions.values() if v.document_id == document_id]
        chunk_ids = [c.id for c in data.chunks.values() if c.document_id == document_id]
        embeddings = sum(
            1 for vectors in data.vectors.values() for cid in chunk_ids if cid in vectors
        )
        keys = [v.storage_key for v in versions]
        report = DeletionReport(
            document_id=document_id,
            versions=len(versions),
            chunks=len(chunk_ids),
            embeddings=embeddings,
            stored_objects=len(keys),
            executed=not dry_run,
        )
        if not dry_run:
            for cid in chunk_ids:
                data.chunks.pop(cid, None)
                data.published.discard(cid)
                for vectors in data.vectors.values():
                    vectors.pop(cid, None)
            for v in versions:
                data.versions.pop(v.id, None)
            data.documents.pop(document_id, None)
            kb = data.kbs[doc.knowledge_base_id]
            data.kbs[kb.id] = replace(kb, epoch=kb.epoch + 1, updated_at=_now())
        return report, keys


# ---------------------------------------------------------------- indexes


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


class MemoryVectorIndex:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def ensure_space(self, ctx: TenantContext, space: EmbeddingSpace) -> None:
        self.store.data(ctx).vectors.setdefault(space.id, {})

    async def upsert(
        self,
        ctx: TenantContext,
        space: EmbeddingSpace,
        knowledge_base_id: UUID,
        items: Sequence[tuple[UUID, Sequence[float]]],
    ) -> None:
        vectors = self.store.data(ctx).vectors.setdefault(space.id, {})
        for chunk_id, vector in items:
            if len(vector) != space.dimension:
                raise InvalidArgument(
                    f"Vector has {len(vector)} dimensions; the space has {space.dimension}."
                )
            vectors[chunk_id] = list(vector)

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
    ) -> list[ChunkHit]:
        if len(vector) != space.dimension:
            raise InvalidArgument("The query vector has the wrong dimension.")
        data = self.store.data(ctx)
        hits = []
        for chunk_id, stored in data.vectors.get(space.id, {}).items():
            chunk = data.chunks.get(chunk_id)
            if chunk is None or chunk_id not in data.published:
                continue
            if chunk.knowledge_base_id != knowledge_base_id or not matches(filters, chunk.metadata):
                continue
            hits.append(ChunkHit(chunk_id, _cosine(vector, stored)))
        hits.sort(key=lambda h: (-h.score, str(h.chunk_id)))
        return hits[:top_k]

    async def count(
        self, ctx: TenantContext, space: EmbeddingSpace, chunk_ids: Sequence[UUID]
    ) -> int:
        vectors = self.store.data(ctx).vectors.get(space.id, {})
        return sum(1 for cid in chunk_ids if cid in vectors)


def _lexical_terms(text: str) -> list[str]:
    """Lowercase, accent-free word tokens (an approximation of ``unaccent`` + ``tsvector``)."""
    terms = []
    for start, end in token_spans(text):
        token = text[start:end]
        if not token[0].isalnum():
            continue
        decomposed = unicodedata.normalize("NFD", token.lower())
        terms.append("".join(c for c in decomposed if not unicodedata.combining(c)))
    return terms


class MemoryLexicalIndex:
    """BM25 over published chunks (k1=1.2, b=0.75)."""

    name = "memory-bm25"

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def search(
        self,
        ctx: TenantContext,
        knowledge_base_id: UUID,
        text: str,
        top_k: int,
        filters: MetadataFilter | None,
        language: str,
    ) -> list[ChunkHit]:
        data = self.store.data(ctx)
        corpus = [
            c
            for cid, c in data.chunks.items()
            if cid in data.published and c.knowledge_base_id == knowledge_base_id
        ]
        query_terms = set(_lexical_terms(text))
        if not corpus or not query_terms:
            return []
        docs = {c.id: Counter(_lexical_terms(c.text)) for c in corpus}
        avg_len = sum(sum(tf.values()) for tf in docs.values()) / len(docs) or 1.0
        df = {t: sum(1 for tf in docs.values() if t in tf) for t in query_terms}
        n = len(docs)
        hits = []
        for chunk in corpus:
            if not matches(filters, chunk.metadata):
                continue
            tf = docs[chunk.id]
            length = sum(tf.values())
            score = 0.0
            for term in query_terms:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                freq = tf[term]
                score += idf * freq * 2.2 / (freq + 1.2 * (0.25 + 0.75 * length / avg_len))
            if score > 0:
                hits.append(ChunkHit(chunk.id, score))
        hits.sort(key=lambda h: (-h.score, str(h.chunk_id)))
        return hits[:top_k]


FUZZY_THRESHOLD = 0.5  # same value as the PostgreSQL adapter
FUZZY_MAX_WORDS = 16
_STOPWORD_TEXT = (
    "a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sob sobre "
    "e ou mas que se como qual quais quando onde quem ao aos pela pelo pelas pelos entre "
    "the an of in on at by for with without and or but that is are was were be to from "
    "it this these those which who whom what when where how"
)
_FUZZY_STOPWORDS = frozenset(_STOPWORD_TEXT.split())


def _trigrams(word: str) -> frozenset[str]:
    """The trigrams of a word as ``pg_trgm`` builds them: two spaces before, one after."""
    padded = f"  {word} "
    return frozenset(padded[i : i + 3] for i in range(len(padded) - 2))


class MemoryFuzzyIndex:
    """Fuzzy search by trigram similarity of words, like the PostgreSQL ``pg_trgm`` adapter.

    The score of a chunk is the sum, over the query words, of the best similarity with a word of
    the chunk, counted only from 0.5. The similarity of a query word is the share of its trigrams
    that the chunk word has (``word_similarity`` of ``pg_trgm``). An approximation for tests and
    small bases.
    """

    name = "memory-trigram"

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def search(
        self,
        ctx: TenantContext,
        knowledge_base_id: UUID,
        text: str,
        top_k: int,
        filters: MetadataFilter | None,
        language: str,
    ) -> list[ChunkHit]:
        words = [
            w
            for w in dict.fromkeys(_lexical_terms(text))
            if len(w) >= 3 and w not in _FUZZY_STOPWORDS
        ][:FUZZY_MAX_WORDS]
        if not words:
            return []
        wanted = {w: _trigrams(w) for w in words}
        data = self.store.data(ctx)
        hits = []
        for cid, chunk in data.chunks.items():
            if cid not in data.published or chunk.knowledge_base_id != knowledge_base_id:
                continue
            if not matches(filters, chunk.metadata):
                continue
            chunk_trigrams = [_trigrams(w) for w in set(_lexical_terms(chunk.text))]
            score = 0.0
            for grams in wanted.values():
                best = max((len(grams & other) / len(grams) for other in chunk_trigrams), default=0)
                if best >= FUZZY_THRESHOLD:
                    score += best
            if score > 0:
                hits.append(ChunkHit(cid, score))
        hits.sort(key=lambda h: (-h.score, str(h.chunk_id)))
        return hits[:top_k]


# ---------------------------------------------------------------- object storage and cache


class MemoryObjectStorage:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def put(self, ctx: TenantContext, key: str, data: bytes, content_type: str) -> None:
        self.store.data(ctx).objects[validate_object_key(key)] = bytes(data)

    async def get(self, ctx: TenantContext, key: str) -> bytes:
        try:
            return self.store.data(ctx).objects[validate_object_key(key)]
        except KeyError:
            raise NotFound(f"Object '{key}' does not exist.") from None

    async def delete(self, ctx: TenantContext, key: str) -> None:
        self.store.data(ctx).objects.pop(validate_object_key(key), None)

    async def delete_prefix(self, ctx: TenantContext, prefix: str) -> int:
        start = validate_object_key(prefix, prefix=True) + "/"
        objects = self.store.data(ctx).objects
        keys = [k for k in objects if k.startswith(start)]
        for k in keys:
            del objects[k]
        return len(keys)


class MemoryCache:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def get(self, ctx: TenantContext, key: str) -> bytes | None:
        entry = self.store.data(ctx).cache.get(key)
        if entry is None or entry[1] < time.monotonic():
            return None
        return entry[0]

    async def set(self, ctx: TenantContext, key: str, value: bytes, ttl_seconds: int) -> None:
        self.store.data(ctx).cache[key] = (value, time.monotonic() + ttl_seconds)

    async def delete_prefix(self, ctx: TenantContext, prefix: str) -> int:
        cache = self.store.data(ctx).cache
        keys = [k for k in cache if k.startswith(prefix)]
        for k in keys:
            del cache[k]
        return len(keys)


class MemoryRateLimiter:
    """Token buckets and daily counters in the process memory (one process only).

    ``clock`` returns the time in seconds since the epoch. Tests replace it.
    """

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self._buckets: dict[tuple[UUID, str], tuple[float, float]] = {}  # tokens, timestamp
        self._days: dict[tuple[UUID, str, str], int] = {}

    async def take(
        self,
        tenant_id: UUID,
        key: str,
        *,
        capacity: int,
        refill_per_second: float,
        cost: int = 1,
    ) -> RateDecision:
        now = self.clock()
        tokens, stamp = self._buckets.get((tenant_id, key), (float(capacity), now))
        tokens = min(float(capacity), tokens + max(now - stamp, 0.0) * refill_per_second)
        allowed = tokens >= cost
        if allowed:
            tokens -= cost
        self._buckets[(tenant_id, key)] = (tokens, now)
        retry = 0.0 if allowed else (cost - tokens) / refill_per_second
        return RateDecision(allowed=allowed, retry_after_seconds=retry, remaining=tokens)

    async def count_day(self, tenant_id: UUID, key: str, *, increment: bool) -> int:
        day = datetime.fromtimestamp(self.clock(), UTC).strftime("%Y%m%d")
        slot = (tenant_id, key, day)
        for old in [s for s in self._days if s[0] == tenant_id and s[1] == key and s[2] != day]:
            del self._days[old]
        if increment:
            self._days[slot] = self._days.get(slot, 0) + 1
        return self._days.get(slot, 0)


# ---------------------------------------------------------------- jobs, audit, tenants


class MemoryJobQueue:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def enqueue(
        self,
        ctx: TenantContext,
        *,
        kind: JobKind,
        knowledge_base_id: UUID | None,
        input: Metadata,
    ) -> IngestionJob:
        job = IngestionJob(
            id=uuid7(),
            tenant_id=ctx.tenant_id,
            kind=kind,
            status=JobStatus.PENDING,
            input=dict(input),
            knowledge_base_id=knowledge_base_id,
            requested_by=ctx.principal_id,
            created_at=_now(),
        )
        self.store.data(ctx).jobs[job.id] = job
        return job

    async def get(self, ctx: TenantContext, job_id: UUID) -> IngestionJob:
        job = self.store.data(ctx).jobs.get(job_id)
        if job is None:
            raise NotFound("Job does not exist.")
        return job

    async def claim(self, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        pending = [
            (job.created_at or _now(), tenant_id, job)
            for tenant_id, data in self.store.all_data()
            for job in data.jobs.values()
            if job.status == JobStatus.PENDING
        ]
        if not pending:
            return None
        _, tenant_id, job = min(pending, key=lambda p: (p[0], str(p[2].id)))
        claimed = replace(job, status=JobStatus.RUNNING, attempt=job.attempt + 1, started_at=_now())
        self.store.data(tenant_id).jobs[job.id] = claimed
        self.store.leases[job.id] = _JobLease(worker_id, _now() + timedelta(seconds=lease_seconds))
        ctx = TenantContext(
            tenant_id=tenant_id,
            principal_id=job.requested_by or tenant_id,
            roles=frozenset({Role.ADMIN}),
            interface="worker",
        )
        return ClaimedJob(job=claimed, ctx=ctx)

    async def heartbeat(self, job_id: UUID, worker_id: str, lease_seconds: int) -> None:
        lease = self.store.leases.get(job_id)
        if lease and lease.worker_id == worker_id:
            lease.until = _now() + timedelta(seconds=lease_seconds)

    async def record_step(self, ctx: TenantContext, job_id: UUID, step: IngestionStep) -> None:
        job = await self.get(ctx, job_id)
        steps = [s for s in job.steps if s.name != step.name or s.document_id != step.document_id]
        self.store.data(ctx).jobs[job_id] = replace(job, steps=(*steps, step))

    async def complete(self, ctx: TenantContext, job_id: UUID, result: Metadata) -> None:
        job = await self.get(ctx, job_id)
        self.store.data(ctx).jobs[job_id] = replace(
            job, status=JobStatus.SUCCEEDED, result=dict(result), finished_at=_now()
        )
        self.store.leases.pop(job_id, None)

    async def fail(
        self, ctx: TenantContext, job_id: UUID, error: Metadata, *, retry: bool, max_attempts: int
    ) -> None:
        job = await self.get(ctx, job_id)
        again = retry and job.attempt < max_attempts
        self.store.data(ctx).jobs[job_id] = replace(
            job,
            status=JobStatus.PENDING if again else JobStatus.FAILED,
            error=dict(error),
            finished_at=None if again else _now(),
        )
        self.store.leases.pop(job_id, None)

    async def requeue_expired(self, max_attempts: int) -> int:
        count = 0
        now = _now()
        for _, data in self.store.all_data():
            for job in list(data.jobs.values()):
                lease = self.store.leases.get(job.id)
                if job.status != JobStatus.RUNNING or lease is None or lease.until > now:
                    continue
                again = job.attempt < max_attempts
                data.jobs[job.id] = replace(
                    job,
                    status=JobStatus.PENDING if again else JobStatus.FAILED,
                    error={"code": "lease_expired", "message": "Worker lease expired."},
                )
                self.store.leases.pop(job.id, None)
                count += 1
        return count


class MemoryAuditLog:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def record(self, ctx: TenantContext, event: AuditEvent) -> None:
        self.store.data(ctx).audit.append(replace(event, created_at=_now()))

    async def record_query(self, ctx: TenantContext, entry: QueryLogEntry) -> None:
        self.store.data(ctx).queries.append(entry)

    async def list_events(
        self,
        ctx: TenantContext,
        *,
        action: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        events = [
            e
            for e in reversed(self.store.data(ctx).audit)
            if (action is None or e.action == action) and (outcome is None or e.outcome == outcome)
        ]
        return events[: max(limit, 0)]


class MemoryTenantDirectory:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def create_tenant(self, slug: str, name: str) -> Tenant:
        if any(t.slug == slug for t in self.store.tenants.values()):
            raise Conflict(f"Tenant '{slug}' already exists.")
        tenant = Tenant(id=uuid7(), slug=slug, name=name)
        self.store.tenants[tenant.id] = tenant
        return tenant

    async def get_tenant(self, slug: str) -> Tenant:
        for tenant in self.store.tenants.values():
            if tenant.slug == slug:
                return tenant
        raise NotFound(f"Tenant '{slug}' does not exist.")

    def _audit(
        self, tenant_id: UUID, action: str, resource_id: str, details: Mapping[str, object]
    ) -> None:
        self.store.data(tenant_id).audit.append(
            AuditEvent(
                tenant_id=tenant_id,
                interface="cli",
                action=action,
                outcome="success",
                resource_type="tenant" if action.startswith("tenant.") else "api_key",
                resource_id=resource_id,
                details=details,
                created_at=_now(),
            )
        )

    async def get_quotas(self, tenant_id: UUID) -> TenantQuotas:
        tenant = self.store.tenants.get(tenant_id)
        if tenant is None:
            raise NotFound("Tenant does not exist.")
        return TenantQuotas.from_settings(tenant.settings)

    async def set_quotas(self, tenant_id: UUID, quotas: TenantQuotas) -> None:
        tenant = self.store.tenants.get(tenant_id)
        if tenant is None:
            raise NotFound("Tenant does not exist.")
        settings = {**tenant.settings, "quotas": quotas.to_settings()}
        self.store.tenants[tenant_id] = replace(tenant, settings=settings)
        self._audit(tenant_id, "tenant.quota_update", str(tenant_id), quotas.to_settings())

    async def issue_api_key(
        self, tenant_id: UUID, *, principal_name: str, roles: frozenset[Role]
    ) -> IssuedApiKey:
        if tenant_id not in self.store.tenants:
            raise NotFound("Tenant does not exist.")
        key, prefix, secret = generate_api_key()
        principal_id = uuid7()
        self.store.keys[prefix] = _KeyRecord(
            tenant_id,
            principal_id,
            hash_secret(secret, self.store.pepper),
            roles,
            principal_name=principal_name,
        )
        self._audit(
            tenant_id,
            "api_key.issue",
            prefix,
            {"principal": principal_name, "roles": sorted(r.value for r in roles)},
        )
        return IssuedApiKey(key=key, key_prefix=prefix, principal_id=principal_id, roles=roles)

    async def list_api_keys(self, tenant_id: UUID) -> list[ApiKeyInfo]:
        return [
            ApiKeyInfo(prefix, r.principal_id, r.principal_name, r.roles, r.revoked)
            for prefix, r in self.store.keys.items()
            if r.tenant_id == tenant_id
        ]

    async def revoke_api_key(self, tenant_id: UUID, key_prefix: str) -> None:
        record = self.store.keys.get(key_prefix)
        if record is None or record.tenant_id != tenant_id:
            raise NotFound("API key does not exist.")
        record.revoked = True
        self._audit(tenant_id, "api_key.revoke", key_prefix, {})

    async def authenticate(self, api_key: str, *, interface: str) -> TenantContext:
        from vlade_rag.core.domain.api_keys import verify_secret

        prefix, secret = parse_api_key(api_key)
        record = self.store.keys.get(prefix)
        if (
            record is None
            or record.revoked
            or not verify_secret(secret, self.store.pepper, record.key_hash)
        ):
            raise Unauthenticated("Invalid API key.")
        return TenantContext(
            tenant_id=record.tenant_id,
            principal_id=record.principal_id,
            roles=record.roles,
            interface=interface,  # type: ignore[arg-type]
        )


@dataclass
class MemoryAdapters:
    store: MemoryStore
    repository: MemoryKnowledgeRepository
    vector_index: MemoryVectorIndex
    lexical_index: MemoryLexicalIndex
    fuzzy_index: MemoryFuzzyIndex
    object_storage: MemoryObjectStorage
    cache: MemoryCache
    rate_limiter: MemoryRateLimiter
    job_queue: MemoryJobQueue
    audit_log: MemoryAuditLog
    tenants: MemoryTenantDirectory


def memory_adapters(store: MemoryStore | None = None) -> MemoryAdapters:
    store = store or MemoryStore()
    return MemoryAdapters(
        store=store,
        repository=MemoryKnowledgeRepository(store),
        vector_index=MemoryVectorIndex(store),
        lexical_index=MemoryLexicalIndex(store),
        fuzzy_index=MemoryFuzzyIndex(store),
        object_storage=MemoryObjectStorage(store),
        cache=MemoryCache(store),
        rate_limiter=MemoryRateLimiter(),
        job_queue=MemoryJobQueue(store),
        audit_log=MemoryAuditLog(store),
        tenants=MemoryTenantDirectory(store),
    )


__all__ = [
    "MemoryAdapters",
    "MemoryAuditLog",
    "MemoryCache",
    "MemoryFuzzyIndex",
    "MemoryJobQueue",
    "MemoryKnowledgeRepository",
    "MemoryLexicalIndex",
    "MemoryObjectStorage",
    "MemoryRateLimiter",
    "MemoryStore",
    "MemoryTenantDirectory",
    "MemoryVectorIndex",
    "SpaceStatus",
    "memory_adapters",
]
