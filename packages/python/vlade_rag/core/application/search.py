"""Retrieval: retrievers, fusion, reranking and the Search use case (ARCHITECTURE 11.1, 11.2)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from vlade_rag.core.application import semconv as sc
from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import (
    ChunkHit,
    InvalidArgument,
    KnowledgeBase,
    MetadataFilter,
    Query,
    QueryLogEntry,
    Role,
    ScoredChunk,
    TenantContext,
    matches,
    parse_filter,
)
from vlade_rag.core.domain.models import JsonValue
from vlade_rag.core.ports import AttrValue, GraphIndex, LexicalIndex

EMBEDDING_CACHE_TTL = 7 * 24 * 3600
SEARCH_CACHE_TTL = 10 * 60


async def _load(
    deps: Dependencies, ctx: TenantContext, hits: list[ChunkHit], retriever: str
) -> list[ScoredChunk]:
    chunks = {c.id: c for c in await deps.repository.get_chunks(ctx, [h.chunk_id for h in hits])}
    return [
        ScoredChunk(chunks[h.chunk_id], h.score, rank, retriever)
        for rank, h in enumerate((h for h in hits if h.chunk_id in chunks), start=1)
    ]


class DenseRetriever:
    name = "dense"

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def retrieve(
        self, ctx: TenantContext, kb: KnowledgeBase, query: Query, top_k: int
    ) -> list[ScoredChunk]:
        space = await self.deps.repository.get_embedding_space(ctx, kb.active_embedding_space_id)
        vector = await self._embed_query(ctx, kb, space.id, query.text)
        with self.deps.tracer.span(
            "retrieval.dense", {sc.SPAN_KIND: sc.RETRIEVER, "vlade.top_k": top_k}
        ):
            hits = await self.deps.vector_index.search(
                ctx,
                space,
                kb.id,
                vector,
                top_k,
                query.filters,
                ef_search=kb.config.retrieval.hnsw_ef_search,
            )
        return await _load(self.deps, ctx, hits, self.name)

    async def _embed_query(
        self, ctx: TenantContext, kb: KnowledgeBase, space_id: UUID, text: str
    ) -> list[float]:
        cache = self.deps.cache
        key = f"emb:{space_id}:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
        if cache is not None:
            cached = await cache.get(ctx, key)
            if cached is not None:
                return [float(x) for x in json.loads(cached)]
        vector = await self.deps.embeddings(kb.config.embeddings).embed_query(text)
        if cache is not None:
            await cache.set(ctx, key, json.dumps(vector).encode(), EMBEDDING_CACHE_TTL)
        return vector


class LexicalRetriever:
    def __init__(self, deps: Dependencies, name: str, index: LexicalIndex) -> None:
        self.deps = deps
        self.name = name
        self.index = index

    async def retrieve(
        self, ctx: TenantContext, kb: KnowledgeBase, query: Query, top_k: int
    ) -> list[ScoredChunk]:
        with self.deps.tracer.span(
            f"retrieval.{self.name}", {sc.SPAN_KIND: sc.RETRIEVER, "vlade.top_k": top_k}
        ):
            hits = await self.index.search(
                ctx, kb.id, query.text, top_k, query.filters, query.language or kb.language
            )
        return await _load(self.deps, ctx, hits, self.name)


def require_graph(deps: Dependencies, kb: KnowledgeBase) -> GraphIndex:
    """The graph index of the base, or ``InvalidArgument`` when the base cannot use it."""
    if deps.graph_index is None:
        raise InvalidArgument("The knowledge graph is not configured on this server.")
    if not kb.config.graph.enabled:
        raise InvalidArgument(f"The knowledge graph is not enabled for the base '{kb.slug}'.")
    return deps.graph_index


async def published_graph_hits(
    deps: Dependencies,
    ctx: TenantContext,
    kb: KnowledgeBase,
    hits: Sequence[ChunkHit],
    filters: MetadataFilter | None,
) -> list[ChunkHit]:
    """Keep the graph hits whose chunk is published and matches the metadata filter.

    The graph keeps the chunks of a version until the next graph job replaces it, so a hit can
    point to an older version.
    """
    published = await deps.repository.published_chunks(ctx, kb.id, [h.chunk_id for h in hits])
    return [h for h in hits if h.chunk_id in published and matches(filters, published[h.chunk_id])]


class GraphRetriever:
    """Chunks reached through the entities and relations of the graph (phase 6, ADR-0032)."""

    name = "graph"

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def retrieve(
        self, ctx: TenantContext, kb: KnowledgeBase, query: Query, top_k: int
    ) -> list[ScoredChunk]:
        graph = require_graph(self.deps, kb)
        cfg = kb.config.graph
        with self.deps.tracer.span(
            "retrieval.graph", {sc.SPAN_KIND: sc.RETRIEVER, "vlade.top_k": top_k}
        ):
            result = await graph.search(ctx, kb, query.text, mode=cfg.mode, top_k=cfg.top_k)
        hits = await published_graph_hits(self.deps, ctx, kb, result.chunk_hits, query.filters)
        return await _load(self.deps, ctx, hits[:top_k], self.name)


@dataclass(frozen=True, slots=True)
class SearchResult:
    knowledge_base: KnowledgeBase
    results: list[ScoredChunk]
    trace_id: str | None


class Search:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    def _retrievers(
        self, kb: KnowledgeBase
    ) -> list[DenseRetriever | LexicalRetriever | GraphRetriever]:
        retrievers: list[DenseRetriever | LexicalRetriever | GraphRetriever] = []
        for name in kb.config.retrieval.retrievers:
            if name == "dense":
                retrievers.append(DenseRetriever(self.deps))
            elif name == "graph":
                require_graph(self.deps, kb)
                retrievers.append(GraphRetriever(self.deps))
            elif name in self.deps.lexical_indexes:
                retrievers.append(
                    LexicalRetriever(self.deps, name, self.deps.lexical_indexes[name])
                )
            else:
                raise InvalidArgument(f"Retriever '{name}' is not configured on this server.")
        return retrievers

    async def execute(
        self,
        ctx: TenantContext,
        *,
        knowledge_base: str,
        text: str,
        top_k: int = 8,
        filters: Mapping[str, JsonValue] | None = None,
        rerank: bool | None = None,
    ) -> SearchResult:
        ctx.require(Role.READER)
        started = time.perf_counter()
        attributes: dict[str, AttrValue] = {
            sc.SPAN_KIND: sc.RETRIEVER,
            "vlade.knowledge_base": knowledge_base,
        }
        content = self.deps.limits.store_query_text
        if content:
            attributes[sc.INPUT_VALUE] = text
        with self.deps.tracer.span("search", attributes) as span:
            kb = await self.deps.repository.get_knowledge_base(ctx, knowledge_base)
            query = Query(self.validate_text(text), kb.id, parse_filter(filters))
            results = await self.run(ctx, kb, query, self.validate_top_k(top_k), rerank)
            for key, value in sc.documents(results, content).items():
                span.set_attribute(key, value)
            await self._log(ctx, kb, query.text, len(results), started)
            trace_id = self.deps.tracer.current_trace_id()
        metrics = self.deps.metrics
        metrics.counter(
            "vlade_requests_total",
            1,
            {"interface": ctx.interface, "operation": "search", "outcome": "success"},
        )
        metrics.histogram(
            "vlade_request_duration_seconds",
            time.perf_counter() - started,
            {"interface": ctx.interface, "operation": "search"},
        )
        return SearchResult(kb, results, trace_id)

    def validate_text(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise InvalidArgument("The query must not be empty.")
        if len(text) > self.deps.limits.max_query_chars:
            raise InvalidArgument(
                f"The query has {len(text)} characters; the limit is "
                f"{self.deps.limits.max_query_chars}."
            )
        return text

    def validate_top_k(self, top_k: int) -> int:
        if not 1 <= top_k <= self.deps.limits.max_top_k:
            raise InvalidArgument(f"top_k must be between 1 and {self.deps.limits.max_top_k}.")
        return top_k

    async def run(
        self,
        ctx: TenantContext,
        kb: KnowledgeBase,
        query: Query,
        top_k: int,
        rerank: bool | None = None,
    ) -> list[ScoredChunk]:
        started = time.perf_counter()
        cfg = kb.config.retrieval
        use_rerank = cfg.rerank.enabled if rerank is None else rerank
        if use_rerank and self.deps.rerankers is None:
            raise InvalidArgument("Reranking is not configured on this server.")
        retrievers = self._retrievers(kb)
        cache_key = self._cache_key(kb, query, top_k, use_rerank)
        cached = await self._cache_get(ctx, cache_key)
        if cached is not None:
            return cached
        vector: list[float] | None = None
        if self._semantic_enabled(query, cfg):
            space = await self.deps.repository.get_embedding_space(
                ctx, kb.active_embedding_space_id
            )
            vector = await DenseRetriever(self.deps)._embed_query(ctx, kb, space.id, query.text)
            records = await self.deps.semantic_cache.lookup(ctx, kb.id, kb.epoch, vector)
            if records is not None:
                hits = await self._rehydrate(ctx, records)
                if hits is not None:
                    return hits
        queries = await self._transform(ctx, kb, query)
        # One list per (query, retriever). The original query keeps the plain retriever name, so
        # the weights of the fusion and the tie-break (ARCHITECTURE 11.2) still apply to it. The
        # lists of a derived query are named "dense#1", "lexical#1", and so on.
        jobs = [
            (r.name if i == 0 else f"{r.name}#{i}", r, q)
            for i, q in enumerate(queries)
            for r in retrievers
            if q.retrievers is None or r.name in q.retrievers
        ]
        lists = await asyncio.gather(
            *(r.retrieve(ctx, kb, q, cfg.top_k_per_retriever) for _, r, q in jobs)
        )
        candidates = max(top_k, cfg.rerank.candidates) if use_rerank else top_k
        with self.deps.tracer.span("fusion", {sc.SPAN_KIND: sc.CHAIN, "vlade.lists": len(jobs)}):
            fused = self.deps.fusion.fuse(
                {name: results for (name, _, _), results in zip(jobs, lists, strict=True)},
                candidates,
            )
        if use_rerank and self.deps.rerankers is not None and fused:
            top_n = min(top_k, cfg.rerank.top_n)
            rerank_started = time.perf_counter()
            with self.deps.tracer.span(
                "rerank",
                {
                    sc.SPAN_KIND: sc.RERANKER,
                    sc.RERANKER_MODEL_NAME: cfg.rerank.model,
                    sc.RERANKER_TOP_K: top_n,
                    "vlade.candidates": len(fused),
                },
            ):
                reranker = self.deps.rerankers(cfg.rerank)
                fused = await reranker.rerank(query.text, fused, top_n)
            self.deps.metrics.histogram(
                "vlade_stage_duration_seconds",
                time.perf_counter() - rerank_started,
                {"stage": "rerank", "adapter": cfg.rerank.model},
            )
        results = fused[:top_k]
        await self._cache_put(ctx, cache_key, results)
        if vector is not None:
            await self.deps.semantic_cache.store(
                ctx, kb.id, kb.epoch, vector, self._records(results)
            )
        metrics = self.deps.metrics
        for (name, _, _), found in zip(jobs, lists, strict=True):
            # A derived query names its lists "dense#1": keep the low-cardinality retriever name.
            metrics.histogram(
                "vlade_retrieval_results", float(len(found)), {"retriever": name.split("#")[0]}
            )
        metrics.histogram(
            "vlade_stage_duration_seconds",
            time.perf_counter() - started,
            {"stage": "retrieval", "adapter": "+".join(r.name for r in retrievers)},
        )
        return results

    async def _transform(self, ctx: TenantContext, kb: KnowledgeBase, query: Query) -> list[Query]:
        """Apply ``retrieval.query_transform``. The first query returned is the original one."""
        mode = kb.config.retrieval.query_transform
        if mode == "none":
            return [query]
        transformer = self.deps.query_transformers.get(mode)
        if transformer is None:
            raise InvalidArgument(f"Query transform '{mode}' is not configured on this server.")
        with self.deps.tracer.span(
            "query_transform", {sc.SPAN_KIND: sc.CHAIN, "vlade.transform": mode}
        ) as span:
            queries = await transformer.transform(ctx, kb, query)
            span.set_attribute("vlade.queries", len(queries))
        # A transformer must keep the original query first. Enforce it here, so a faulty plugin
        # cannot make the search lose the question of the user.
        rest = [q for q in queries if q != query]
        return [query, *rest]

    # Result cache (ARCHITECTURE 11.6). The key holds the base epoch: publishing, deleting or
    # reindexing bumps it, so an old entry is never read again and needs no sweep.

    @staticmethod
    def _cache_key(kb: KnowledgeBase, query: Query, top_k: int, use_rerank: bool) -> str:
        spec = {
            "text": query.text,
            "language": query.language,
            "filters": repr(query.filters),
            "top_k": top_k,
            "rerank": use_rerank,
            "retrieval": kb.config.retrieval.model_dump(mode="json"),
        }
        digest = hashlib.sha256(
            json.dumps(spec, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return f"search:{kb.id}:{kb.epoch}:{digest}"

    def _semantic_enabled(self, query: Query, cfg: Any) -> bool:
        """Only plain dense searches use the semantic cache. Derived queries and filters do not."""
        settings = self.deps.semantic_cache.settings
        return (
            settings.enabled
            and self.deps.cache is not None
            and "dense" in cfg.retrievers
            and cfg.query_transform == "none"
            and query.filters is None
        )

    @staticmethod
    def _records(results: Sequence[ScoredChunk]) -> list[dict[str, Any]]:
        return [
            {"id": str(r.chunk.id), "score": r.score, "retriever": r.retriever} for r in results
        ]

    async def _rehydrate(
        self, ctx: TenantContext, entries: Sequence[Mapping[str, Any]]
    ) -> list[ScoredChunk] | None:
        try:
            ids = [UUID(str(e["id"])) for e in entries]
            chunks = {c.id: c for c in await self.deps.repository.get_chunks(ctx, ids)}
            if any(i not in chunks for i in ids):
                return None
            return [
                ScoredChunk(
                    chunks[UUID(str(e["id"]))], float(e["score"]), rank, str(e["retriever"])
                )
                for rank, e in enumerate(entries, start=1)
            ]
        except (ValueError, KeyError, TypeError):
            return None

    async def _cache_get(self, ctx: TenantContext, key: str) -> list[ScoredChunk] | None:
        if self.deps.cache is None:
            return None
        raw = await self.deps.cache.get(ctx, key)
        if raw is None:
            return None
        try:
            entries = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return await self._rehydrate(ctx, entries)

    async def _cache_put(self, ctx: TenantContext, key: str, results: list[ScoredChunk]) -> None:
        if self.deps.cache is None:
            return
        await self.deps.cache.set(
            ctx, key, json.dumps(self._records(results)).encode(), SEARCH_CACHE_TTL
        )

    async def _log(
        self, ctx: TenantContext, kb: KnowledgeBase, text: str, count: int, started: float
    ) -> None:
        await self.deps.audit_log.record_query(
            ctx,
            QueryLogEntry(
                interface=ctx.interface,
                mode="search",
                query_hash=hashlib.sha256(text.encode("utf-8")).digest(),
                result_count=count,
                latency_ms=int((time.perf_counter() - started) * 1000),
                knowledge_base_id=kb.id,
                principal_id=ctx.principal_id,
                query_text=text if self.deps.limits.store_query_text else None,
                trace_id=self.deps.tracer.current_trace_id(),
            ),
        )
