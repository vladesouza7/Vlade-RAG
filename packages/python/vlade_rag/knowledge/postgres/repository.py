"""PostgreSQL KnowledgeRepository (docs/ARCHITECTURE.md section 7)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

import asyncpg

from vlade_rag.core.domain import (
    Chunk,
    ChunkDraft,
    Conflict,
    DeletionReport,
    Distance,
    Document,
    DocumentVersion,
    EmbeddingSpace,
    KnowledgeBase,
    KnowledgeBaseConfig,
    Metadata,
    NotFound,
    SpaceStatus,
    TenantContext,
    TenantUsage,
    VersionStatus,
    uuid7,
)
from vlade_rag.knowledge.postgres.db import PostgresDatabase

TEXT_SEARCH_CONFIG = {"pt": "vlade_pt", "en": "vlade_en"}


def text_search_config(language: str) -> str:
    return TEXT_SEARCH_CONFIG.get(language.split("-")[0].lower(), "simple")


def _kb(row: Mapping[str, Any]) -> KnowledgeBase:
    return KnowledgeBase(
        id=row["id"],
        tenant_id=row["tenant_id"],
        slug=row["slug"],
        name=row["name"],
        config=KnowledgeBaseConfig.model_validate(row["config"]),
        active_embedding_space_id=row["active_embedding_space_id"],
        epoch=row["epoch"],
    )


def _document(row: Mapping[str, Any]) -> Document:
    return Document(
        id=row["id"],
        tenant_id=row["tenant_id"],
        knowledge_base_id=row["knowledge_base_id"],
        title=row["title"],
        mime_type=row["mime_type"],
        source_type=row["source_type"],
        external_id=row["external_id"],
        source_uri=row["source_uri"],
        current_version_id=row["current_version_id"],
        metadata=row["metadata"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _version(row: Mapping[str, Any]) -> DocumentVersion:
    return DocumentVersion(
        id=row["id"],
        tenant_id=row["tenant_id"],
        document_id=row["document_id"],
        version=row["version"],
        content_hash=row["content_hash"],
        storage_key=row["storage_key"],
        size_bytes=row["size_bytes"],
        status=VersionStatus(row["status"]),
    )


def _chunk(row: Mapping[str, Any]) -> Chunk:
    return Chunk(
        id=row["id"],
        tenant_id=row["tenant_id"],
        knowledge_base_id=row["knowledge_base_id"],
        document_id=row["document_id"],
        document_version_id=row["document_version_id"],
        ordinal=row["ordinal"],
        text=row["text"],
        token_count=row["token_count"],
        start_offset=row["start_offset"],
        end_offset=row["end_offset"],
        page=row["page"],
        section=row["section"],
        metadata=row["metadata"],
        document_title=row["document_title"],
    )


_CHUNK_COLUMNS = """c.id, c.tenant_id, c.knowledge_base_id, c.document_id, c.document_version_id,
c.ordinal, c.text, c.token_count, c.start_offset, c.end_offset, c.page, c.section, c.metadata,
d.title AS document_title"""


class PostgresKnowledgeRepository:
    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db

    # ------------------------------------------------------------ knowledge bases

    async def create_knowledge_base(
        self, ctx: TenantContext, *, slug: str, name: str, config: KnowledgeBaseConfig
    ) -> KnowledgeBase:
        emb = config.embeddings
        space_id, kb_id = uuid7(), uuid7()
        async with self.db.tenant(ctx) as conn:
            try:
                await conn.execute(
                    "INSERT INTO embedding_spaces (id, tenant_id, provider, model, dimension, "
                    "version) VALUES ($1, $2, $3, $4, $5, 1)",
                    space_id,
                    ctx.tenant_id,
                    emb.provider,
                    emb.model,
                    emb.dimension,
                )
                row = await conn.fetchrow(
                    "INSERT INTO knowledge_bases (id, tenant_id, slug, name, language, config, "
                    "active_embedding_space_id) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
                    kb_id,
                    ctx.tenant_id,
                    slug,
                    name,
                    config.language,
                    config.model_dump(mode="json"),
                    space_id,
                )
            except asyncpg.UniqueViolationError:
                raise Conflict(f"Knowledge base '{slug}' already exists.") from None
        return _kb(row)

    async def get_knowledge_base(self, ctx: TenantContext, slug: str) -> KnowledgeBase:
        async with self.db.tenant(ctx) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM knowledge_bases WHERE tenant_id = $1 AND slug = $2",
                ctx.tenant_id,
                slug,
            )
        if row is None:
            raise NotFound(f"Knowledge base '{slug}' does not exist.")
        return _kb(row)

    async def get_knowledge_base_by_id(self, ctx: TenantContext, kb_id: UUID) -> KnowledgeBase:
        async with self.db.tenant(ctx) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM knowledge_bases WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                kb_id,
            )
        if row is None:
            raise NotFound("Knowledge base does not exist.")
        return _kb(row)

    async def list_knowledge_bases(self, ctx: TenantContext) -> list[KnowledgeBase]:
        async with self.db.tenant(ctx) as conn:
            rows = await conn.fetch(
                "SELECT * FROM knowledge_bases WHERE tenant_id = $1 ORDER BY slug", ctx.tenant_id
            )
        return [_kb(r) for r in rows]

    async def count_documents(self, ctx: TenantContext, kb_id: UUID) -> int:
        async with self.db.tenant(ctx) as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM documents WHERE tenant_id = $1 AND knowledge_base_id = $2",
                ctx.tenant_id,
                kb_id,
            )
        return int(count)

    async def get_usage(self, ctx: TenantContext) -> TenantUsage:
        async with self.db.tenant(ctx) as conn:
            documents = await conn.fetchval(
                "SELECT count(*) FROM documents WHERE tenant_id = $1", ctx.tenant_id
            )
            size = await conn.fetchval(
                "SELECT COALESCE(sum(size_bytes), 0) FROM document_versions "
                "WHERE tenant_id = $1 AND status IN ('indexing', 'published')",
                ctx.tenant_id,
            )
        return TenantUsage(documents=int(documents), bytes=int(size))

    async def get_embedding_space(self, ctx: TenantContext, space_id: UUID) -> EmbeddingSpace:
        async with self.db.tenant(ctx) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM embedding_spaces WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                space_id,
            )
        if row is None:
            raise NotFound("Embedding space does not exist.")
        return EmbeddingSpace(
            id=row["id"],
            tenant_id=row["tenant_id"],
            provider=row["provider"],
            model=row["model"],
            dimension=row["dimension"],
            version=row["version"],
            distance=Distance(row["distance"]),
            status=SpaceStatus(row["status"]),
        )

    # ------------------------------------------------------------ documents

    async def find_document(
        self, ctx: TenantContext, *, knowledge_base_id: UUID, external_id: str
    ) -> Document | None:
        async with self.db.tenant(ctx) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM documents WHERE tenant_id = $1 AND knowledge_base_id = $2 "
                "AND external_id = $3",
                ctx.tenant_id,
                knowledge_base_id,
                external_id,
            )
        return None if row is None else _document(row)

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
        async with self.db.tenant(ctx) as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM knowledge_bases WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                knowledge_base_id,
            )
            if not exists:
                raise NotFound("Knowledge base does not exist.")
            row = await conn.fetchrow(
                "INSERT INTO documents (id, tenant_id, knowledge_base_id, external_id, source_type,"
                " source_uri, title, mime_type, metadata) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) "
                "ON CONFLICT (knowledge_base_id, external_id) DO UPDATE SET "
                "source_type = EXCLUDED.source_type, source_uri = EXCLUDED.source_uri, "
                "title = EXCLUDED.title, mime_type = EXCLUDED.mime_type, "
                "metadata = EXCLUDED.metadata, updated_at = now() RETURNING *",
                uuid7(),
                ctx.tenant_id,
                knowledge_base_id,
                external_id,
                source_type,
                source_uri,
                title,
                mime_type,
                dict(metadata),
            )
        return _document(row)

    async def get_document(self, ctx: TenantContext, document_id: UUID) -> Document:
        async with self.db.tenant(ctx) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM documents WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                document_id,
            )
        if row is None:
            raise NotFound("Document does not exist.")
        return _document(row)

    async def create_version(
        self,
        ctx: TenantContext,
        *,
        document_id: UUID,
        content_hash: str,
        storage_key: str,
        size_bytes: int,
    ) -> DocumentVersion:
        async with self.db.tenant(ctx) as conn:
            locked = await conn.fetchval(
                "SELECT 1 FROM documents WHERE tenant_id = $1 AND id = $2 FOR UPDATE",
                ctx.tenant_id,
                document_id,
            )
            if not locked:
                raise NotFound("Document does not exist.")
            row = await conn.fetchrow(
                "INSERT INTO document_versions (id, tenant_id, document_id, version, content_hash,"
                " storage_key, size_bytes) SELECT $1, $2, $3, coalesce(max(version), 0) + 1, $4,"
                " $5, $6 FROM document_versions WHERE document_id = $3 RETURNING *",
                uuid7(),
                ctx.tenant_id,
                document_id,
                content_hash,
                storage_key,
                size_bytes,
            )
        return _version(row)

    async def get_version(self, ctx: TenantContext, version_id: UUID) -> DocumentVersion:
        async with self.db.tenant(ctx) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM document_versions WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                version_id,
            )
        if row is None:
            raise NotFound("Document version does not exist.")
        return _version(row)

    async def get_current_version(
        self, ctx: TenantContext, document_id: UUID
    ) -> DocumentVersion | None:
        async with self.db.tenant(ctx) as conn:
            row = await conn.fetchrow(
                "SELECT v.* FROM documents d JOIN document_versions v "
                "ON v.id = d.current_version_id WHERE d.tenant_id = $1 AND d.id = $2",
                ctx.tenant_id,
                document_id,
            )
        return None if row is None else _version(row)

    async def mark_version_failed(self, ctx: TenantContext, version_id: UUID) -> None:
        async with self.db.tenant(ctx) as conn:
            await conn.execute(
                "UPDATE document_versions SET status = 'failed' WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                version_id,
            )

    # ------------------------------------------------------------ chunks

    async def save_chunks(
        self,
        ctx: TenantContext,
        version: DocumentVersion,
        drafts: Sequence[ChunkDraft],
        *,
        language: str,
    ) -> list[Chunk]:
        config = text_search_config(language)
        async with self.db.tenant(ctx) as conn:
            doc = await conn.fetchrow(
                "SELECT * FROM documents WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                version.document_id,
            )
            if doc is None:
                raise NotFound("Document does not exist.")
            await conn.execute(
                "DELETE FROM chunks WHERE tenant_id = $1 AND document_version_id = $2",
                ctx.tenant_id,
                version.id,
            )
            rows = [
                (
                    uuid7(),
                    ctx.tenant_id,
                    doc["knowledge_base_id"],
                    doc["id"],
                    version.id,
                    d.ordinal,
                    d.text,
                    d.token_count,
                    d.page,
                    d.start_offset,
                    d.end_offset,
                    d.section,
                    {**doc["metadata"], **d.metadata},
                    config,
                )
                for d in drafts
            ]
            await conn.executemany(
                "INSERT INTO chunks (id, tenant_id, knowledge_base_id, document_id, "
                "document_version_id, ordinal, text, token_count, page, start_offset, end_offset, "
                "section, metadata, tsv) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,"
                "to_tsvector($14::regconfig, coalesce($12, '') || ' ' || $7))",
                rows,
            )
            saved = await conn.fetch(
                f"SELECT {_CHUNK_COLUMNS} FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE c.tenant_id = $1 AND c.document_version_id = $2 ORDER BY c.ordinal",
                ctx.tenant_id,
                version.id,
            )
        return [_chunk(r) for r in saved]

    async def get_chunks(self, ctx: TenantContext, chunk_ids: Sequence[UUID]) -> list[Chunk]:
        if not chunk_ids:
            return []
        async with self.db.tenant(ctx) as conn:
            rows = await conn.fetch(
                f"SELECT {_CHUNK_COLUMNS} FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE c.tenant_id = $1 AND c.id = ANY($2::uuid[])",
                ctx.tenant_id,
                list(chunk_ids),
            )
        by_id = {r["id"]: _chunk(r) for r in rows}
        return [by_id[cid] for cid in chunk_ids if cid in by_id]

    async def list_chunks(self, ctx: TenantContext, version_id: UUID) -> list[Chunk]:
        async with self.db.tenant(ctx) as conn:
            rows = await conn.fetch(
                f"SELECT {_CHUNK_COLUMNS} FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE c.tenant_id = $1 AND c.document_version_id = $2 ORDER BY c.ordinal",
                ctx.tenant_id,
                version_id,
            )
        return [_chunk(r) for r in rows]

    # ------------------------------------------------------------ publication and deletion

    async def publish_version(self, ctx: TenantContext, version_id: UUID) -> None:
        async with self.db.tenant(ctx) as conn:
            version = await conn.fetchrow(
                "SELECT document_id FROM document_versions WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                version_id,
            )
            if version is None:
                raise NotFound("Document version does not exist.")
            doc = await conn.fetchrow(
                "SELECT id, current_version_id, knowledge_base_id FROM documents "
                "WHERE tenant_id = $1 AND id = $2 FOR UPDATE",
                ctx.tenant_id,
                version["document_id"],
            )
            old = doc["current_version_id"]
            if old is not None and old != version_id:
                await conn.execute(
                    "UPDATE chunks SET is_published = false WHERE document_version_id = $1", old
                )
                await conn.execute(
                    "UPDATE document_versions SET status = 'superseded' WHERE id = $1", old
                )
            await conn.execute(
                "UPDATE chunks SET is_published = true WHERE document_version_id = $1", version_id
            )
            await conn.execute(
                "UPDATE document_versions SET status = 'published', published_at = now() "
                "WHERE id = $1",
                version_id,
            )
            await conn.execute(
                "UPDATE documents SET current_version_id = $1, updated_at = now() WHERE id = $2",
                version_id,
                doc["id"],
            )
            await conn.execute(
                "UPDATE knowledge_bases SET epoch = epoch + 1, updated_at = now() WHERE id = $1",
                doc["knowledge_base_id"],
            )

    async def delete_document(
        self, ctx: TenantContext, document_id: UUID, *, dry_run: bool
    ) -> tuple[DeletionReport, list[str]]:
        async with self.db.tenant(ctx) as conn:
            doc = await conn.fetchrow(
                "SELECT id, knowledge_base_id FROM documents WHERE tenant_id = $1 AND id = $2 "
                "FOR UPDATE",
                ctx.tenant_id,
                document_id,
            )
            if doc is None:
                raise NotFound("Document does not exist.")
            keys = [
                r["storage_key"]
                for r in await conn.fetch(
                    "SELECT storage_key FROM document_versions WHERE document_id = $1", document_id
                )
            ]
            chunks = await conn.fetchval(
                "SELECT count(*) FROM chunks WHERE document_id = $1", document_id
            )
            embeddings = await conn.fetchval(
                "SELECT count(*) FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id "
                "WHERE c.document_id = $1",
                document_id,
            )
            if not dry_run:
                await conn.execute("DELETE FROM documents WHERE id = $1", document_id)
                await conn.execute(
                    "UPDATE knowledge_bases SET epoch = epoch + 1 WHERE id = $1",
                    doc["knowledge_base_id"],
                )
        report = DeletionReport(
            document_id=document_id,
            versions=len(keys),
            chunks=int(chunks),
            embeddings=int(embeddings),
            stored_objects=len(keys),
            executed=not dry_run,
        )
        return report, keys
