"""``GraphIndex`` adapter with LightRAG (phase 6, ADR-0032). Needs the ``graph`` extra.

Design:
- One LightRAG instance per base, with the workspace ``t<tenant hex>_k<kb hex>``. The adapter
  derives it from the caller context and the base; user input never names a workspace.
- Storage in a PostgreSQL database separate from the main one: ``PGKVStorage``,
  ``PGVectorStorage``, ``PGTableGraphStorage`` (no Apache AGE) and ``PGDocStatusStorage``.
- The chunks are the Vlade-RAG chunks (``ainsert_custom_chunks``), with the version id as the
  LightRAG document id. The table ``vlade_graph_chunks`` maps the SHA-256 of a chunk text back
  to the Vlade-RAG chunk id, so graph results fuse with the other retrievers.
- The extraction LLM and the embeddings are the providers of the runtime (OpenRouter, OpenCode,
  any OpenAI-compatible API). Nothing runs a local model.

LightRAG reads its PostgreSQL connection from process environment variables (``POSTGRES_*``).
The adapter sets them from ``VLADE_GRAPH__DATABASE_URL`` once, when it starts.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import UUID

import asyncpg
import numpy as np
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc

from vlade_rag.core.config.settings import GraphSettings
from vlade_rag.core.domain import (
    Chunk,
    ChunkHit,
    GenerationParams,
    KnowledgeBase,
    Message,
    ProviderUnavailable,
    TenantContext,
)
from vlade_rag.core.domain.kb_config import EmbeddingsConfig, GenerationConfig
from vlade_rag.core.ports import (
    EmbeddingProvider,
    GraphEntity,
    GraphRelation,
    GraphSearchResult,
    LLMProvider,
)

logger = logging.getLogger(__name__)

_MAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS vlade_graph_versions (
  workspace   text NOT NULL,
  document_id uuid NOT NULL,
  version_id  uuid NOT NULL,
  PRIMARY KEY (workspace, document_id, version_id)
);
CREATE TABLE IF NOT EXISTS vlade_graph_chunks (
  workspace      text NOT NULL,
  chunk_id       uuid NOT NULL,
  version_id     uuid NOT NULL,
  content_sha256 text NOT NULL,
  PRIMARY KEY (workspace, chunk_id)
);
CREATE INDEX IF NOT EXISTS vlade_graph_chunks_sha_idx
  ON vlade_graph_chunks (workspace, content_sha256);
"""


def workspace_of(ctx: TenantContext, kb: KnowledgeBase) -> str:
    """LightRAG workspace of a base. Hex ids: no separator, no user input."""
    return f"t{ctx.tenant_id.hex}_k{kb.id.hex}"


def content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _configure_environment(url: str, max_connections: int) -> None:
    parts = urlsplit(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    os.environ.update(
        {
            "POSTGRES_HOST": parts.hostname or "127.0.0.1",
            "POSTGRES_PORT": str(parts.port or 5432),
            "POSTGRES_USER": unquote(parts.username or ""),
            "POSTGRES_PASSWORD": unquote(parts.password or ""),
            "POSTGRES_DATABASE": parts.path.lstrip("/") or "postgres",
            "POSTGRES_MAX_CONNECTIONS": str(max_connections),
        }
    )


class LightRAGGraphIndex:
    name = "lightrag"

    def __init__(
        self,
        settings: GraphSettings,
        llms: Callable[[GenerationConfig], LLMProvider],
        embeddings: Callable[[EmbeddingsConfig], EmbeddingProvider],
    ) -> None:
        if settings.database_url is None:
            raise ValueError("VLADE_GRAPH__DATABASE_URL is required for the LightRAG graph.")
        self.settings = settings
        self.url = settings.database_url.get_secret_value().replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )
        self.llms = llms
        self.embeddings = embeddings
        self._instances: OrderedDict[tuple[str, str], LightRAG] = OrderedDict()
        self._lock = asyncio.Lock()
        self._pool: asyncpg.Pool | None = None
        _configure_environment(self.url, settings.max_connections)

    # ------------------------------------------------------------ infrastructure

    async def _db(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.url, min_size=0, max_size=4)
            async with self._pool.acquire() as conn:
                await conn.execute(_MAP_SCHEMA)
        return self._pool

    async def ping(self) -> None:
        pool = await self._db()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

    def _llm_func(self, kb: KnowledgeBase) -> Callable[..., Any]:
        cfg = kb.config.graph
        provider = self.llms(GenerationConfig(provider=cfg.provider, model=cfg.model))
        params = GenerationParams(
            model=cfg.model, temperature=0.0, max_output_tokens=cfg.max_output_tokens
        )

        async def complete(
            prompt: str,
            system_prompt: str | None = None,
            history_messages: Sequence[dict[str, str]] | None = None,
            **_: Any,
        ) -> str:
            messages = [Message("system", system_prompt)] if system_prompt else []
            for item in history_messages or ():
                role = item.get("role", "user")
                messages.append(
                    Message(role if role in ("user", "assistant") else "user", item["content"])  # type: ignore[arg-type]
                )
            messages.append(Message("user", prompt))
            generation = await provider.generate(messages, params)
            return generation.text

        return complete

    def _embedding_func(self, kb: KnowledgeBase) -> EmbeddingFunc:
        cfg = kb.config.embeddings
        provider = self.embeddings(cfg)

        async def embed(texts: list[str], **_: Any) -> np.ndarray:
            vectors = await provider.embed_documents(texts)
            return np.array(vectors, dtype=np.float32)

        # model_name gives each embedding model its own vector tables (LightRAG suffix).
        model = "".join(c if c.isalnum() else "_" for c in f"{cfg.provider}_{cfg.model}")
        return EmbeddingFunc(
            embedding_dim=cfg.dimension,
            max_token_size=8192,
            func=embed,
            model_name=f"{model}_{cfg.dimension}"[:48],
        )

    @staticmethod
    def _fingerprint(kb: KnowledgeBase) -> str:
        g, e = kb.config.graph, kb.config.embeddings
        return f"{g.provider}|{g.model}|{g.max_output_tokens}|{e.provider}|{e.model}|{e.dimension}"

    async def _rag(self, ctx: TenantContext, kb: KnowledgeBase) -> LightRAG:
        key = (workspace_of(ctx, kb), self._fingerprint(kb))
        async with self._lock:
            rag = self._instances.get(key)
            if rag is not None:
                self._instances.move_to_end(key)
                return rag
            for old_key in [k for k in self._instances if k[0] == key[0]]:
                await self._instances.pop(old_key).finalize_storages()  # configuration changed
            rag = LightRAG(
                working_dir=self.settings.working_dir,
                workspace=key[0],
                kv_storage="PGKVStorage",
                vector_storage="PGVectorStorage",
                graph_storage="PGTableGraphStorage",
                doc_status_storage="PGDocStatusStorage",
                llm_model_func=self._llm_func(kb),
                llm_model_max_async=self.settings.llm_max_async,
                embedding_func=self._embedding_func(kb),
            )
            await rag.initialize_storages()
            self._instances[key] = rag
            while len(self._instances) > self.settings.max_instances:
                _, evicted = self._instances.popitem(last=False)
                await evicted.finalize_storages()
            return rag

    async def aclose(self) -> None:
        async with self._lock:
            while self._instances:
                _, rag = self._instances.popitem()
                await rag.finalize_storages()
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    # ------------------------------------------------------------ GraphIndex

    async def index_document(
        self,
        ctx: TenantContext,
        kb: KnowledgeBase,
        document_id: UUID,
        version_id: UUID,
        chunks: Sequence[Chunk],
    ) -> int:
        workspace = workspace_of(ctx, kb)
        rag = await self._rag(ctx, kb)
        pool = await self._db()
        async with pool.acquire() as conn:
            older = [
                r["version_id"]
                for r in await conn.fetch(
                    "SELECT version_id FROM vlade_graph_versions "
                    "WHERE workspace = $1 AND document_id = $2 AND version_id <> $3",
                    workspace,
                    document_id,
                    version_id,
                )
            ]
        for old in older:
            await self._delete_version(rag, pool, workspace, old)
        texts = [c.text for c in chunks if c.text.strip()]
        if not texts:
            return 0
        try:
            await rag.ainsert_custom_chunks("\n\n".join(texts), texts, doc_id=str(version_id))
        except ProviderUnavailable:
            raise
        except Exception as exc:  # LightRAG wraps provider errors in its own exceptions
            raise ProviderUnavailable(f"LightRAG could not index the document: {exc}") from exc
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO vlade_graph_versions (workspace, document_id, version_id) "
                "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                workspace,
                document_id,
                version_id,
            )
            await conn.executemany(
                "INSERT INTO vlade_graph_chunks (workspace, chunk_id, version_id, content_sha256) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT (workspace, chunk_id) DO NOTHING",
                [(workspace, c.id, version_id, content_sha256(c.text)) for c in chunks],
            )
        return len(texts)

    async def _delete_version(
        self, rag: LightRAG, pool: asyncpg.Pool, workspace: str, version_id: UUID
    ) -> None:
        await rag.adelete_by_doc_id(str(version_id))
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "DELETE FROM vlade_graph_chunks WHERE workspace = $1 AND version_id = $2",
                workspace,
                version_id,
            )
            await conn.execute(
                "DELETE FROM vlade_graph_versions WHERE workspace = $1 AND version_id = $2",
                workspace,
                version_id,
            )

    async def delete_document(
        self, ctx: TenantContext, kb: KnowledgeBase, document_id: UUID
    ) -> int:
        workspace = workspace_of(ctx, kb)
        pool = await self._db()
        async with pool.acquire() as conn:
            versions = [
                r["version_id"]
                for r in await conn.fetch(
                    "SELECT version_id FROM vlade_graph_versions "
                    "WHERE workspace = $1 AND document_id = $2",
                    workspace,
                    document_id,
                )
            ]
        if not versions:
            return 0
        rag = await self._rag(ctx, kb)
        for version_id in versions:
            await self._delete_version(rag, pool, workspace, version_id)
        return len(versions)

    async def search(
        self, ctx: TenantContext, kb: KnowledgeBase, text: str, *, mode: str, top_k: int
    ) -> GraphSearchResult:
        workspace = workspace_of(ctx, kb)
        rag = await self._rag(ctx, kb)
        param = QueryParam(
            mode=mode,
            top_k=top_k,
            chunk_top_k=top_k,
            enable_rerank=False,  # Vlade-RAG reranks after the fusion
        )
        try:
            result = await rag.aquery_data(text, param)
        except Exception as exc:
            raise ProviderUnavailable(f"LightRAG query failed: {exc}") from exc
        if result.get("status") != "success":
            logger.warning("LightRAG query returned %s", result.get("message"))
            return GraphSearchResult()
        data = result.get("data", {})
        entities = tuple(
            GraphEntity(
                name=str(e.get("entity_name", "")),
                type=str(e.get("entity_type", "")),
                description=str(e.get("description", "")),
            )
            for e in data.get("entities", [])
        )
        relations = tuple(
            GraphRelation(
                source=str(r.get("src_id", "")),
                target=str(r.get("tgt_id", "")),
                keywords=str(r.get("keywords", "")),
                description=str(r.get("description", "")),
                weight=float(r.get("weight") or 1.0),
            )
            for r in data.get("relationships", [])
        )
        hashes = [content_sha256(str(c.get("content", ""))) for c in data.get("chunks", [])]
        hits: list[ChunkHit] = []
        if hashes:
            pool = await self._db()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT content_sha256, chunk_id FROM vlade_graph_chunks "
                    "WHERE workspace = $1 AND content_sha256 = ANY($2::text[])",
                    workspace,
                    hashes,
                )
            by_hash: dict[str, list[UUID]] = {}
            for row in rows:
                by_hash.setdefault(row["content_sha256"], []).append(row["chunk_id"])
            seen: set[UUID] = set()
            for rank, digest in enumerate(hashes, start=1):
                for chunk_id in by_hash.get(digest, []):
                    if chunk_id not in seen:
                        seen.add(chunk_id)
                        hits.append(ChunkHit(chunk_id, 1.0 / rank))
        return GraphSearchResult(entities=entities, relations=relations, chunk_hits=tuple(hits))
