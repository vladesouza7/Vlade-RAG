"""Reindex without downtime (docs/ARCHITECTURE.md section 13, ADR-0027).

``ReindexKnowledgeBase`` checks the request, shows a preview or queues a ``reindex`` job.
``ReindexRunner`` runs the job in the worker:

- ``embeddings`` mode: a new embedding space is built next to the active one, then made active
  in one transaction. Searches keep using the active space until the switch, so no search mixes
  vectors of two spaces.
- ``full`` mode: the new chunking is stored, and every document gets a new version and an
  ingestion job from its original file. Each document switches when its job publishes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import (
    AuditEvent,
    Chunk,
    Conflict,
    EmbeddingSpace,
    IngestionJob,
    IngestionStep,
    InvalidArgument,
    JobKind,
    JobStatus,
    KnowledgeBase,
    Metadata,
    MissingVectors,
    Role,
    TenantContext,
)
from vlade_rag.core.domain.kb_config import ChunkingConfig, EmbeddingsConfig

ReindexMode = Literal["embeddings", "full"]
PAGE = 512  # chunks read from the repository at a time
CATCH_UP_ROUNDS = 5  # passes over the chunks published during the build, before the switch
VERSION_STEP = "reindex.version"  # marks a document already handled by a full reindex job


@dataclass(frozen=True, slots=True)
class ReindexPreview:
    knowledge_base: str
    mode: ReindexMode
    documents: int
    chunks: int
    estimated_embedding_calls: int
    embeddings: EmbeddingsConfig | None
    chunking: ChunkingConfig | None


@dataclass(frozen=True, slots=True)
class ReindexResult:
    executed: bool
    preview: ReindexPreview
    job: IngestionJob | None = None


class ReindexKnowledgeBase:
    """Preview or queue a reindex. Needs the admin role."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(
        self,
        ctx: TenantContext,
        *,
        knowledge_base: str,
        mode: str,
        embeddings: Mapping[str, Any] | None = None,
        chunking: Mapping[str, Any] | None = None,
        confirm: bool = False,
    ) -> ReindexResult:
        """``embeddings`` (mode ``embeddings``) and ``chunking`` (mode ``full``) are partial
        configurations merged over the current one. Without ``confirm``, nothing changes."""
        ctx.require(Role.ADMIN)
        if mode not in ("embeddings", "full"):
            raise InvalidArgument("The mode must be 'embeddings' or 'full'.")
        repo = self.deps.repository
        kb = await repo.get_knowledge_base(ctx, knowledge_base)
        new_embeddings: EmbeddingsConfig | None = None
        new_chunking: ChunkingConfig | None = None
        if mode == "embeddings":
            if chunking:
                raise InvalidArgument("The embeddings mode does not change the chunking.")
            new_embeddings = _merge(kb.config.embeddings, embeddings, "embeddings")
        else:
            if embeddings:
                raise InvalidArgument(
                    "The full mode keeps the embedding model. Run the embeddings mode first."
                )
            new_chunking = _merge(kb.config.chunking, chunking, "chunking")
        active = await self.deps.job_queue.find_active(ctx, kb.id, JobKind.REINDEX)
        if active is not None:
            raise Conflict(
                f"A reindex of this knowledge base is already running (job {active.id})."
            )

        documents = await repo.count_documents(ctx, kb.id)
        chunks = await _count_published(self.deps, ctx, kb.id)
        batch = (new_embeddings or kb.config.embeddings).batch_size
        preview = ReindexPreview(
            knowledge_base=kb.slug,
            mode=mode,  # type: ignore[arg-type]
            documents=documents,
            chunks=chunks,
            estimated_embedding_calls=math.ceil(chunks / batch) if chunks else 0,
            embeddings=new_embeddings,
            chunking=new_chunking,
        )
        if not confirm:
            return ReindexResult(executed=False, preview=preview)

        job_input: dict[str, Any] = {"mode": mode}
        if new_embeddings is not None:
            job_input["embeddings"] = new_embeddings.model_dump(mode="json")
        if new_chunking is not None:
            job_input["chunking"] = new_chunking.model_dump(mode="json")
        job = await self.deps.job_queue.enqueue(
            ctx, kind=JobKind.REINDEX, knowledge_base_id=kb.id, input=job_input
        )
        await self.deps.audit_log.record(
            ctx,
            AuditEvent(
                tenant_id=ctx.tenant_id,
                principal_id=ctx.principal_id,
                interface=ctx.interface,
                action="knowledge_base.reindex",
                outcome="success",
                resource_type="knowledge_base",
                resource_id=str(kb.id),
                details={"mode": mode, "job_id": str(job.id), "chunks": chunks},
            ),
        )
        return ReindexResult(executed=True, preview=preview, job=job)


class ReindexRunner:
    """Run a ``reindex`` job (worker side)."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def run(self, ctx: TenantContext, job: IngestionJob) -> Metadata:
        if job.knowledge_base_id is None:
            raise InvalidArgument("The job has no knowledge base.")
        kb = await self.deps.repository.get_knowledge_base_by_id(ctx, job.knowledge_base_id)
        mode = job.input.get("mode")
        if mode == "embeddings":
            config = EmbeddingsConfig.model_validate(job.input["embeddings"])
            return await self._embeddings(ctx, kb, config)
        if mode == "full":
            chunking = ChunkingConfig.model_validate(job.input["chunking"])
            return await self._full(ctx, kb, chunking, job)
        raise InvalidArgument(f"Unknown reindex mode '{mode}'.")

    # ------------------------------------------------------------ embeddings mode

    async def _embeddings(
        self, ctx: TenantContext, kb: KnowledgeBase, config: EmbeddingsConfig
    ) -> Metadata:
        repo, tracer = self.deps.repository, self.deps.tracer
        provider = self.deps.embeddings(config)
        if provider.dimension != config.dimension:
            raise InvalidArgument(
                f"The model gives {provider.dimension} dimensions; the configuration says "
                f"{config.dimension}."
            )
        space = await repo.create_embedding_space(ctx, config)
        await self.deps.vector_index.ensure_space(ctx, space)
        embedded = 0
        with tracer.span("reindex.build", {"vlade.space_id": str(space.id)}):
            after = None
            while chunks := await repo.list_published_chunks(ctx, kb.id, after=after, limit=PAGE):
                embedded += await self._index(ctx, kb, space, config, chunks)
                after = chunks[-1].id
        with tracer.span("reindex.switch", {"vlade.space_id": str(space.id)}):
            for _ in range(CATCH_UP_ROUNDS):
                # Chunks published while the build ran have vectors only in the old space.
                while missing := await repo.list_chunks_without_vector(
                    ctx, kb.id, space.id, limit=PAGE
                ):
                    embedded += await self._index(ctx, kb, space, config, missing)
                try:
                    old = await repo.activate_embedding_space(ctx, kb.id, space.id, config)
                    break
                except MissingVectors:
                    continue  # a document was published between the pass and the switch
            else:
                raise MissingVectors(
                    "The base kept receiving documents; the new space never caught up."
                )
        await self.deps.audit_log.record(
            ctx,
            AuditEvent(
                tenant_id=ctx.tenant_id,
                principal_id=ctx.principal_id,
                interface=ctx.interface,
                action="knowledge_base.embedding_space.activate",
                outcome="success",
                resource_type="knowledge_base",
                resource_id=str(kb.id),
                details={"space_id": str(space.id), "retired_space_id": str(old)},
            ),
        )
        return {
            "mode": "embeddings",
            "new_space_id": str(space.id),
            "retired_space_id": str(old),
            "model": config.model,
            "dimension": config.dimension,
            "chunks_embedded": embedded,
        }

    async def _index(
        self,
        ctx: TenantContext,
        kb: KnowledgeBase,
        space: EmbeddingSpace,
        config: EmbeddingsConfig,
        chunks: Sequence[Chunk],
    ) -> int:
        provider = self.deps.embeddings(config)
        batch = max(1, min(config.batch_size, provider.max_batch_size))
        for i in range(0, len(chunks), batch):
            part = chunks[i : i + batch]
            vectors = await provider.embed_documents(
                [f"{c.document_title}\n\n{c.text}" for c in part]
            )
            if len(vectors) != len(part) or any(len(v) != space.dimension for v in vectors):
                raise InvalidArgument("The embedding provider returned vectors of the wrong size.")
            await self.deps.vector_index.upsert(
                ctx, space, kb.id, list(zip((c.id for c in part), vectors, strict=True))
            )
        return len(chunks)

    # ------------------------------------------------------------ full mode

    async def _full(
        self,
        ctx: TenantContext,
        kb: KnowledgeBase,
        chunking: ChunkingConfig,
        job: IngestionJob,
    ) -> Metadata:
        repo, queue = self.deps.repository, self.deps.job_queue
        documents = await repo.list_current_versions(ctx, kb.id)
        # A crashed worker makes the queue requeue the same job. The steps of that job tell us
        # which documents already have a version and an ingestion job, so we do not create them
        # again (roadmap 4.4).
        handled = {
            step.document_id
            for step in job.steps
            if step.name == VERSION_STEP and step.document_id is not None
        }
        jobs = 0
        for document, current in documents:
            if document.id in handled:
                continue
            version = await repo.create_version(
                ctx,
                document_id=document.id,
                content_hash=current.content_hash,
                storage_key=current.storage_key,
                size_bytes=current.size_bytes,
            )
            await queue.enqueue(
                ctx,
                kind=JobKind.INGEST,
                knowledge_base_id=kb.id,
                input={
                    "document_id": str(document.id),
                    "version_id": str(version.id),
                    "filename": document.title,
                    "mime_type": document.mime_type,
                    # The job carries its own chunking and the version it may replace. A normal
                    # ingestion that publishes during the reindex is not overwritten (ADR-0027).
                    "expected_version_id": str(current.id),
                    "chunking": chunking.model_dump(mode="json"),
                },
            )
            now = datetime.now(UTC)
            await queue.record_step(
                ctx,
                job.id,
                IngestionStep(
                    VERSION_STEP,
                    JobStatus.SUCCEEDED,
                    job.attempt,
                    document.id,
                    None,
                    now,
                    now,
                ),
            )
            jobs += 1
        # Store the new chunking only after every document has a job. A failure before this
        # point leaves extra versions and jobs, but not a base rechunked only in part.
        latest = await repo.get_knowledge_base_by_id(ctx, kb.id)
        config = latest.config.model_copy(update={"chunking": chunking})
        await repo.update_knowledge_base_config(ctx, kb.id, config)
        return {"mode": "full", "documents": len(documents), "ingestion_jobs": jobs}


def _merge(current: Any, override: Mapping[str, Any] | None, name: str) -> Any:
    data = {**current.model_dump(), **dict(override or {})}
    try:
        return type(current).model_validate(data)
    except ValidationError as exc:
        raise InvalidArgument(f"Invalid {name} configuration: {exc.errors()[0]['msg']}") from exc


async def _count_published(deps: Dependencies, ctx: TenantContext, kb_id: UUID) -> int:
    total, after = 0, None
    while chunks := await deps.repository.list_published_chunks(
        ctx, kb_id, after=after, limit=PAGE
    ):
        total += len(chunks)
        after = chunks[-1].id
    return total
