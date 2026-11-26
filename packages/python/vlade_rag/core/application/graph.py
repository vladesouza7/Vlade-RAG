"""Knowledge graph use cases (phase 6, ADR-0032).

The graph is optional per base (``graph.enabled``) and per server (``Dependencies.graph_index``).
Ingestion enqueues a ``graph_index`` job after a version is published. The graph job never marks
the document version as failed: the vector index of that version stays valid.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from vlade_rag.core.application import semconv as sc
from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.application.search import (
    Search,
    _load,
    published_graph_hits,
    require_graph,
)
from vlade_rag.core.domain import (
    AuditEvent,
    IngestionJob,
    InvalidArgument,
    JobKind,
    KnowledgeBase,
    Metadata,
    NotFound,
    Role,
    ScoredChunk,
    TenantContext,
)
from vlade_rag.core.ports import GraphEntity, GraphRelation

# Job input key of the graph job. It is not "version_id" on purpose: a failed graph job must not
# mark the document version as failed.
GRAPH_VERSION_KEY = "graph_version_id"
GRAPH_MODES = ("local", "global", "hybrid", "mix", "naive")


async def enqueue_graph_index(
    deps: Dependencies,
    ctx: TenantContext,
    kb: KnowledgeBase,
    document_id: UUID,
    version_id: UUID,
) -> IngestionJob | None:
    """Enqueue the graph job of a published version. None when the base has no graph."""
    if deps.graph_index is None or not kb.config.graph.enabled:
        return None
    return await deps.job_queue.enqueue(
        ctx,
        kind=JobKind.GRAPH_INDEX,
        knowledge_base_id=kb.id,
        input={"document_id": str(document_id), GRAPH_VERSION_KEY: str(version_id)},
    )


class GraphIndexRunner:
    """Worker side of a ``graph_index`` job."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def run(self, ctx: TenantContext, job: IngestionJob) -> Metadata:
        repo = self.deps.repository
        if job.knowledge_base_id is None:
            raise InvalidArgument("The job has no knowledge base.")
        kb = await repo.get_knowledge_base_by_id(ctx, job.knowledge_base_id)
        graph = require_graph(self.deps, kb)
        document_id = UUID(str(job.input["document_id"]))
        version_id = UUID(str(job.input[GRAPH_VERSION_KEY]))
        try:
            current = await repo.get_current_version(ctx, document_id)
        except NotFound:
            removed = await graph.delete_document(ctx, kb, document_id)
            return {"document_id": str(document_id), "skipped": True, "removed": removed}
        if current is None or current.id != version_id:
            # A newer version was published; its own graph job replaces this one.
            return {"document_id": str(document_id), "skipped": True}
        chunks = await repo.list_chunks(ctx, version_id)
        limit = kb.config.graph.max_chunks_per_document
        if len(chunks) > limit:
            raise InvalidArgument(
                f"The document has {len(chunks)} chunks; graph.max_chunks_per_document is {limit}."
            )
        with self.deps.tracer.span(
            "graph.index", {sc.SPAN_KIND: sc.CHAIN, "vlade.chunks": len(chunks)}
        ):
            indexed = await graph.index_document(ctx, kb, document_id, version_id, chunks)
        return {
            "document_id": str(document_id),
            "version_id": str(version_id),
            "chunks": indexed,
            "skipped": False,
        }


@dataclass(frozen=True, slots=True)
class GraphSearchView:
    knowledge_base: KnowledgeBase
    entities: tuple[GraphEntity, ...]
    relations: tuple[GraphRelation, ...]
    chunks: list[ScoredChunk]
    trace_id: str | None


class SearchGraph:
    """Explore the graph of a base: entities, relations and the chunks that support them."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(
        self,
        ctx: TenantContext,
        *,
        knowledge_base: str,
        text: str,
        mode: str | None = None,
        top_k: int | None = None,
    ) -> GraphSearchView:
        ctx.require(Role.READER)
        kb = await self.deps.repository.get_knowledge_base(ctx, knowledge_base)
        graph = require_graph(self.deps, kb)
        cfg = kb.config.graph
        search = Search(self.deps)
        query = search.validate_text(text)
        if mode is not None and mode not in GRAPH_MODES:
            raise InvalidArgument(f"mode must be one of: {', '.join(GRAPH_MODES)}.")
        k = cfg.top_k if top_k is None else top_k
        if not 1 <= k <= 200:
            raise InvalidArgument("top_k must be between 1 and 200.")
        with self.deps.tracer.span("graph.search", {sc.SPAN_KIND: sc.RETRIEVER, "vlade.top_k": k}):
            result = await graph.search(ctx, kb, query, mode=mode or cfg.mode, top_k=k)
        hits = await published_graph_hits(self.deps, ctx, kb, result.chunk_hits, None)
        chunks = await _load(self.deps, ctx, hits[: self.deps.limits.max_top_k], "graph")
        return GraphSearchView(
            knowledge_base=kb,
            entities=result.entities[:k],
            relations=result.relations[:k],
            chunks=chunks,
            trace_id=self.deps.tracer.current_trace_id(),
        )


@dataclass(frozen=True, slots=True)
class GraphReindexResult:
    executed: bool
    documents: int
    jobs: int


class ReindexGraph:
    """Enqueue a graph job for every published document of the base.

    Use it after the graph is enabled on a base with documents, or after a change of the
    extraction model. Without ``confirm`` it only counts the documents.
    """

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(
        self, ctx: TenantContext, *, knowledge_base: str, confirm: bool
    ) -> GraphReindexResult:
        ctx.require(Role.ADMIN)
        repo = self.deps.repository
        kb = await repo.get_knowledge_base(ctx, knowledge_base)
        require_graph(self.deps, kb)
        current = await repo.list_current_versions(ctx, kb.id)
        if not confirm:
            return GraphReindexResult(executed=False, documents=len(current), jobs=0)
        jobs = 0
        for document, version in current:
            if await enqueue_graph_index(self.deps, ctx, kb, document.id, version.id):
                jobs += 1
        await self.deps.audit_log.record(
            ctx,
            AuditEvent(
                tenant_id=ctx.tenant_id,
                principal_id=ctx.principal_id,
                interface=ctx.interface,
                action="graph.reindex",
                outcome="success",
                resource_type="knowledge_base",
                resource_id=str(kb.id),
                details={"documents": len(current), "jobs": jobs},
                trace_id=ctx.trace_id,
            ),
        )
        return GraphReindexResult(executed=True, documents=len(current), jobs=jobs)
