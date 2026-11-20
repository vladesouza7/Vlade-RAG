"""Retrieval: retrievers, fusion, reranking and the Search use case (ARCHITECTURE 11.1, 11.2)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import (
    ChunkHit,
    InvalidArgument,
    KnowledgeBase,
    Query,
    QueryLogEntry,
    Role,
    ScoredChunk,
    TenantContext,
    parse_filter,
)
from vlade_rag.core.domain.models import JsonValue
from vlade_rag.core.ports import LexicalIndex

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
        with self.deps.tracer.span("retrieval.dense", {"vlade.top_k": top_k}):
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
        with self.deps.tracer.span(f"retrieval.{self.name}", {"vlade.top_k": top_k}):
            hits = await self.index.search(
                ctx, kb.id, query.text, top_k, query.filters, query.language or kb.language
            )
        return await _load(self.deps, ctx, hits, self.name)


@dataclass(frozen=True, slots=True)
class SearchResult:
    knowledge_base: KnowledgeBase
    results: list[ScoredChunk]
    trace_id: str | None


class Search:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    def _retrievers(self, kb: KnowledgeBase) -> list[DenseRetriever | LexicalRetriever]:
        retrievers: list[DenseRetriever | LexicalRetriever] = []
        for name in kb.config.retrieval.retrievers:
            if name == "dense":
                retrievers.append(DenseRetriever(self.deps))
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
        kb = await self.deps.repository.get_knowledge_base(ctx, knowledge_base)
        query = Query(self.validate_text(text), kb.id, parse_filter(filters))
        results = await self.run(ctx, kb, query, self.validate_top_k(top_k), rerank)
        await self._log(ctx, kb, query.text, len(results), started)
        return SearchResult(kb, results, self.deps.tracer.current_trace_id())

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
        cfg = kb.config.retrieval
        use_rerank = cfg.rerank.enabled if rerank is None else rerank
        if use_rerank and self.deps.rerankers is None:
            raise InvalidArgument("Reranking is not configured on this server.")
        retrievers = self._retrievers(kb)
        cache_key = self._cache_key(kb, query, top_k, use_rerank)
        cached = await self._cache_get(ctx, cache_key)
        if cached is not None:
            return cached
        lists = await asyncio.gather(
            *(r.retrieve(ctx, kb, query, cfg.top_k_per_retriever) for r in retrievers)
        )
        candidates = max(top_k, cfg.rerank.candidates) if use_rerank else top_k
        with self.deps.tracer.span("fusion", {"vlade.retrievers": len(retrievers)}):
            fused = self.deps.fusion.fuse(
                {r.name: results for r, results in zip(retrievers, lists, strict=True)},
                candidates,
            )
        if use_rerank and self.deps.rerankers is not None and fused:
            with self.deps.tracer.span("rerank", {"vlade.candidates": len(fused)}):
                reranker = self.deps.rerankers(cfg.rerank)
                fused = await reranker.rerank(query.text, fused, min(top_k, cfg.rerank.top_n))
        results = fused[:top_k]
        await self._cache_put(ctx, cache_key, results)
        return results

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

    async def _cache_get(self, ctx: TenantContext, key: str) -> list[ScoredChunk] | None:
        if self.deps.cache is None:
            return None
        raw = await self.deps.cache.get(ctx, key)
        if raw is None:
            return None
        try:
            entries = json.loads(raw)
            ids = [UUID(e["id"]) for e in entries]
            chunks = {c.id: c for c in await self.deps.repository.get_chunks(ctx, ids)}
            if any(i not in chunks for i in ids):
                return None
            return [
                ScoredChunk(chunks[UUID(e["id"])], float(e["score"]), rank, str(e["retriever"]))
                for rank, e in enumerate(entries, start=1)
            ]
        except (ValueError, KeyError, TypeError):
            return None

    async def _cache_put(self, ctx: TenantContext, key: str, results: list[ScoredChunk]) -> None:
        if self.deps.cache is None:
            return
        entries = [
            {"id": str(r.chunk.id), "score": r.score, "retriever": r.retriever} for r in results
        ]
        await self.deps.cache.set(ctx, key, json.dumps(entries).encode(), SEARCH_CACHE_TTL)

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
