"""Ingestion use cases and pipeline (docs/ARCHITECTURE.md section 10)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.application.mime import resolve_mime_type
from vlade_rag.core.domain import (
    AuditEvent,
    Chunk,
    Document,
    EmbeddingSpaceChanged,
    IngestionJob,
    IngestionStep,
    InvalidArgument,
    JobKind,
    JobStatus,
    KnowledgeBase,
    Metadata,
    NotFound,
    ParsedDocument,
    ProviderUnavailable,
    QuotaExceeded,
    RawDocument,
    Role,
    Section,
    TenantContext,
    VladeError,
)
from vlade_rag.core.ports import ChunkingParams, ClaimedJob, TextNormalizer

_HEADING = re.compile(r"^(#{1,6}) +(.+)$", re.MULTILINE)


def document_prefix(kb_id: UUID, document_id: UUID) -> str:
    return f"kb/{kb_id}/docs/{document_id}/"


def original_key(kb_id: UUID, document_id: UUID, content_hash: str) -> str:
    return f"{document_prefix(kb_id, document_id)}{content_hash}/original"


def text_key(kb_id: UUID, document_id: UUID, content_hash: str) -> str:
    return f"{document_prefix(kb_id, document_id)}{content_hash}/text.md"


def normalize_parsed(parsed: ParsedDocument, normalizer: TextNormalizer) -> ParsedDocument:
    """Normalize page by page (keeps page offsets) and detect Markdown headings as sections."""
    if parsed.page_starts:
        bounds = [*parsed.page_starts, len(parsed.text)]
        pages = [
            normalizer.normalize(parsed.text[bounds[i] : bounds[i + 1]])
            for i in range(len(parsed.page_starts))
        ]
        starts: list[int] = []
        parts: list[str] = []
        offset = 0
        for page in pages:
            starts.append(offset)
            if page:
                parts.append(page)
                offset += len(page) + 2
        text = "\n\n".join(parts)
        page_starts = tuple(min(s, max(len(text) - 1, 0)) for s in starts)
    else:
        text = normalizer.normalize(parsed.text)
        page_starts = ()
    headings = list(_HEADING.finditer(text))
    sections = tuple(
        Section(
            title=m.group(2).strip(),
            start_offset=m.start(),
            end_offset=headings[i + 1].start() if i + 1 < len(headings) else len(text),
            level=len(m.group(1)),
        )
        for i, m in enumerate(headings)
    )
    return ParsedDocument(
        text=text,
        title=parsed.title,
        page_starts=page_starts,
        sections=sections,
        metadata=parsed.metadata,
    )


def _audit(ctx: TenantContext, action: str, outcome: str, **kw: object) -> AuditEvent:
    return AuditEvent(
        tenant_id=ctx.tenant_id,
        principal_id=ctx.principal_id,
        interface=ctx.interface,
        action=action,
        outcome=outcome,
        trace_id=ctx.trace_id,
        **kw,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- submit


@dataclass(frozen=True, slots=True)
class SubmitResult:
    job: IngestionJob
    document: Document
    skipped: bool


class SubmitIngestion:
    """Validate and store a document, then enqueue the ingestion job (status ``pending``)."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def _enforce_quotas(
        self, ctx: TenantContext, *, new_document: bool, added_bytes: int, filename: str
    ) -> None:
        """Raise ``QuotaExceeded`` (and audit it) if the file passes a quota of the tenant."""
        if self.deps.tenants is None:
            return
        quotas = await self.deps.tenants.get_quotas(ctx.tenant_id)
        if quotas.documents is None and quotas.bytes is None:
            return
        usage = await self.deps.repository.get_usage(ctx)
        try:
            quotas.check_submit(usage, new_document=new_document, added_bytes=added_bytes)
        except QuotaExceeded as exc:
            await self.deps.audit_log.record(
                ctx,
                _audit(
                    ctx,
                    "document.ingest",
                    "denied",
                    resource_type="document",
                    details={
                        "reason": "quota_exceeded",
                        "filename": filename,
                        "documents": usage.documents,
                        "bytes": usage.bytes,
                        "added_bytes": added_bytes,
                    },
                ),
            )
            raise exc

    async def execute(
        self,
        ctx: TenantContext,
        *,
        knowledge_base: str,
        raw: RawDocument,
        title: str | None = None,
        external_id: str | None = None,
    ) -> SubmitResult:
        ctx.require(Role.WRITER)
        repo = self.deps.repository
        kb = await repo.get_knowledge_base(ctx, knowledge_base)
        if not raw.data:
            raise InvalidArgument("The file is empty.")
        if len(raw.data) > self.deps.limits.max_upload_bytes:
            raise QuotaExceeded(
                f"The file has {len(raw.data)} bytes; the limit is "
                f"{self.deps.limits.max_upload_bytes} bytes."
            )
        mime_type = resolve_mime_type(raw.filename, raw.mime_type, raw.data)
        if self.deps.parser_for(mime_type) is None:
            raise InvalidArgument(f"No parser is configured for '{mime_type}'.")

        content_hash = hashlib.sha256(raw.data).hexdigest()
        existing = (
            await repo.find_document(ctx, knowledge_base_id=kb.id, external_id=external_id)
            if external_id is not None
            else None
        )
        unchanged = False
        if existing is not None:
            existing_version = await repo.get_current_version(ctx, existing.id)
            unchanged = (
                existing_version is not None and existing_version.content_hash == content_hash
            )
        if not unchanged:
            await self._enforce_quotas(
                ctx, new_document=existing is None, added_bytes=len(raw.data), filename=raw.filename
            )

        document = await repo.upsert_document(
            ctx,
            knowledge_base_id=kb.id,
            title=(title or raw.filename).strip()[:500] or raw.filename,
            mime_type=mime_type,
            source_type=raw.source_type,
            external_id=external_id,
            source_uri=raw.source_uri,
            metadata=raw.metadata,
        )
        current = await repo.get_current_version(ctx, document.id)
        if current is not None and current.content_hash == content_hash:
            job = await self.deps.job_queue.enqueue(
                ctx,
                kind=JobKind.INGEST,
                knowledge_base_id=kb.id,
                input={"document_id": str(document.id), "filename": raw.filename},
            )
            result = {"document_id": str(document.id), "skipped": True, "reason": "unchanged"}
            await self.deps.job_queue.complete(ctx, job.id, result)
            job = await self.deps.job_queue.get(ctx, job.id)
            return SubmitResult(job=job, document=document, skipped=True)

        key = original_key(kb.id, document.id, content_hash)
        await self.deps.object_storage.put(ctx, key, raw.data, mime_type)
        version = await repo.create_version(
            ctx,
            document_id=document.id,
            content_hash=content_hash,
            storage_key=key,
            size_bytes=len(raw.data),
        )
        job = await self.deps.job_queue.enqueue(
            ctx,
            kind=JobKind.INGEST,
            knowledge_base_id=kb.id,
            input={
                "document_id": str(document.id),
                "version_id": str(version.id),
                "filename": raw.filename,
                "mime_type": mime_type,
            },
        )
        await self.deps.audit_log.record(
            ctx,
            _audit(
                ctx,
                "document.ingest",
                "success",
                resource_type="document",
                resource_id=str(document.id),
                details={"job_id": str(job.id), "version": version.version},
            ),
        )
        return SubmitResult(job=job, document=document, skipped=False)


# ---------------------------------------------------------------- run


PUBLISH_ATTEMPTS = 3  # embeddings again when a reindex switches the space (ADR-0027)


class _StepFailedError(Exception):
    def __init__(self, step: str, cause: Exception) -> None:
        super().__init__(f"{step}: {cause}")
        self.step = step
        self.cause = cause


class RunIngestionJob:
    """Run the ingestion pipeline for a claimed job (worker side)."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, claimed: ClaimedJob) -> None:
        ctx, job = claimed.ctx, claimed.job
        try:
            if job.kind == JobKind.INGEST:
                result = await self._ingest(ctx, job)
            elif job.kind == JobKind.REINDEX:
                result = await self._reindex(ctx, job)
            else:
                raise _StepFailedError(
                    "dispatch", InvalidArgument(f"Job kind '{job.kind}' is not supported yet.")
                )
        except _StepFailedError as exc:
            cause = exc.cause
            retry = isinstance(cause, ProviderUnavailable)
            error: Mapping[str, object] = {
                "step": exc.step,
                "code": cause.code if isinstance(cause, VladeError) else "internal",
                "message": str(cause) if isinstance(cause, VladeError) else type(cause).__name__,
            }
            version_id = job.input.get("version_id")
            if version_id and not retry:
                await self.deps.repository.mark_version_failed(ctx, UUID(str(version_id)))
            await self.deps.job_queue.fail(
                ctx, job.id, error, retry=retry, max_attempts=self.deps.limits.job_max_attempts
            )
            return
        await self.deps.job_queue.complete(ctx, job.id, result)

    @asynccontextmanager
    async def _step(
        self, ctx: TenantContext, job: IngestionJob, name: str, document_id: UUID | None
    ) -> AsyncIterator[None]:
        started = datetime.now(UTC)
        with self.deps.tracer.span(f"ingestion.{name}", {"vlade.job_id": str(job.id)}):
            await self.deps.job_queue.record_step(
                ctx,
                job.id,
                IngestionStep(name, JobStatus.RUNNING, job.attempt, document_id, None, started),
            )
            try:
                yield
            except Exception as exc:
                error = {"message": str(exc) if isinstance(exc, VladeError) else repr(exc)}
                await self.deps.job_queue.record_step(
                    ctx,
                    job.id,
                    IngestionStep(
                        name,
                        JobStatus.FAILED,
                        job.attempt,
                        document_id,
                        error,
                        started,
                        datetime.now(UTC),
                    ),
                )
                raise _StepFailedError(name, exc) from exc
            await self.deps.job_queue.record_step(
                ctx,
                job.id,
                IngestionStep(
                    name,
                    JobStatus.SUCCEEDED,
                    job.attempt,
                    document_id,
                    None,
                    started,
                    datetime.now(UTC),
                ),
            )

    async def _ingest(self, ctx: TenantContext, job: IngestionJob) -> Metadata:
        deps, repo = self.deps, self.deps.repository
        document_id = UUID(str(job.input["document_id"]))
        version_id = UUID(str(job.input["version_id"]))
        mime_type = str(job.input["mime_type"])
        if job.knowledge_base_id is None:
            raise InvalidArgument("The job has no knowledge base.")
        kb = await repo.get_knowledge_base_by_id(ctx, job.knowledge_base_id)
        document = await repo.get_document(ctx, document_id)
        version = await repo.get_version(ctx, version_id)
        if version.document_id != document_id:
            raise NotFound("Document version does not exist.")

        async with self._step(ctx, job, "extract", document_id):
            parser = deps.parser_for(mime_type)
            if parser is None:
                raise InvalidArgument(f"No parser is configured for '{mime_type}'.")
            data = await deps.object_storage.get(ctx, version.storage_key)
            parsed = await parser.parse(
                RawDocument(
                    filename=str(job.input.get("filename", document.title)),
                    mime_type=mime_type,
                    data=data,
                )
            )
        async with self._step(ctx, job, "normalize", document_id):
            normalized = normalize_parsed(parsed, deps.normalizer)
            if not normalized.text:
                raise InvalidArgument("The document has no text.")
        async with self._step(ctx, job, "chunk", document_id):
            cfg = kb.config.chunking
            drafts = deps.chunker.split(
                normalized, ChunkingParams(cfg.strategy, cfg.max_tokens, cfg.overlap_tokens)
            )
            chunks = await repo.save_chunks(ctx, version, drafts, language=kb.language)
            await deps.object_storage.put(
                ctx,
                text_key(kb.id, document_id, version.content_hash),
                normalized.text.encode("utf-8"),
                "text/markdown",
            )
        for attempt in range(1, PUBLISH_ATTEMPTS + 1):
            async with self._step(ctx, job, "embed", document_id):
                vectors = await self._embed(kb, document, chunks)
            async with self._step(ctx, job, "index_vectors", document_id):
                space = await repo.get_embedding_space(ctx, kb.active_embedding_space_id)
                await deps.vector_index.upsert(
                    ctx, space, kb.id, list(zip((c.id for c in chunks), vectors, strict=True))
                )
            async with self._step(ctx, job, "validate_indexes", document_id):
                indexed = await deps.vector_index.count(ctx, space, [c.id for c in chunks])
                if indexed != len(chunks):
                    raise InvalidArgument(f"{indexed} vectors for {len(chunks)} chunks.")
            try:
                async with self._step(ctx, job, "publish", document_id):
                    await repo.publish_version(ctx, version.id, embedding_space_id=space.id)
                break
            except _StepFailedError as exc:
                # A reindex switched the space after the vectors were written (ADR-0027):
                # embed again with the new model, in the new space.
                if not isinstance(exc.cause, EmbeddingSpaceChanged) or attempt == PUBLISH_ATTEMPTS:
                    raise
                kb = await repo.get_knowledge_base_by_id(ctx, kb.id)
        return {
            "document_id": str(document_id),
            "version_id": str(version.id),
            "version": version.version,
            "chunks": len(chunks),
            "skipped": False,
        }

    async def _reindex(self, ctx: TenantContext, job: IngestionJob) -> Metadata:
        from vlade_rag.core.application.reindex import ReindexRunner

        async with self._step(ctx, job, "reindex", None):
            return await ReindexRunner(self.deps).run(ctx, job)

    async def _embed(
        self, kb: KnowledgeBase, document: Document, chunks: list[Chunk]
    ) -> list[list[float]]:
        provider = self.deps.embeddings(kb.config.embeddings)
        batch = max(1, min(kb.config.embeddings.batch_size, provider.max_batch_size))
        texts = [f"{document.title}\n\n{c.text}" for c in chunks]
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch):
            vectors.extend(await provider.embed_documents(texts[i : i + batch]))
        if any(len(v) != provider.dimension for v in vectors):
            raise InvalidArgument("The embedding provider returned vectors of the wrong size.")
        return vectors


class GetIngestionStatus:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, ctx: TenantContext, job_id: UUID) -> IngestionJob:
        ctx.require(Role.READER)
        return await self.deps.job_queue.get(ctx, job_id)
