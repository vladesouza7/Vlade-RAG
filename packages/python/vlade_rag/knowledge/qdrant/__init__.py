"""Qdrant VectorIndex adapter, an alternative to pgvector (ADR-0004).

pgvector remains the default. Qdrant gets the same port, the same tenant isolation and the
same publication and metadata filters. The client is created lazily, so installations without
the ``qdrant`` extra still import the package.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from vlade_rag.core.config.settings import QdrantSettings
from vlade_rag.core.domain import (
    ChunkHit,
    Distance,
    EmbeddingSpace,
    InvalidArgument,
    Metadata,
    MetadataFilter,
    TenantContext,
)
from vlade_rag.core.domain.query import matches
from vlade_rag.core.ports import KnowledgeRepository

try:
    from qdrant_client import AsyncQdrantClient, models

    _QDRANT_AVAILABLE = True
except ImportError:  # pragma: no cover - the extra is optional
    _QDRANT_AVAILABLE = False

_DISTANCE = {
    Distance.COSINE: "COSINE",
    Distance.DOT: "DOT",
    Distance.L2: "EUCLID",
}


class QdrantVectorIndex:
    """Vector index on Qdrant with one collection per tenant and embedding space.

    The collection name carries the tenant id. A caller cannot read another tenant's points
    even when it passes the space of that tenant. Publication and metadata live in the
    repository, so a search asks the repository which candidates are current.
    """

    def __init__(
        self,
        client: Any,
        repository: KnowledgeRepository,
        *,
        prefix: str = "vlade_",
        oversample: int = 5,
    ) -> None:
        if not _QDRANT_AVAILABLE:
            raise InvalidArgument('The qdrant backend needs the "qdrant" extra.')
        self.client = client
        self.repository = repository
        self.prefix = prefix
        self.oversample = oversample

    @classmethod
    def from_settings(
        cls, settings: QdrantSettings, repository: KnowledgeRepository
    ) -> QdrantVectorIndex:
        if not _QDRANT_AVAILABLE:
            raise InvalidArgument('The qdrant backend needs the "qdrant" extra.')
        client = AsyncQdrantClient(
            url=settings.url,
            api_key=settings.api_key.get_secret_value() if settings.api_key else None,
            timeout=settings.timeout,
        )
        return cls(
            client,
            repository,
            prefix=settings.collection_prefix,
            oversample=settings.oversample,
        )

    def _collection(self, ctx: TenantContext, space: EmbeddingSpace) -> str:
        return f"{self.prefix}{ctx.tenant_id.hex}_{space.id.hex}"

    def _filter(self, ctx: TenantContext, kb_id: UUID | None = None) -> Any:
        must: list[Any] = [
            models.FieldCondition(
                key="tenant_id", match=models.MatchValue(value=str(ctx.tenant_id))
            )
        ]
        if kb_id is not None:
            must.append(
                models.FieldCondition(key="kb_id", match=models.MatchValue(value=str(kb_id)))
            )
        return models.Filter(must=must)

    async def ping(self) -> None:
        await self.client.get_collections()

    async def aclose(self) -> None:
        await self.client.close()

    async def ensure_space(self, ctx: TenantContext, space: EmbeddingSpace) -> None:
        name = self._collection(ctx, space)
        if not await self.client.collection_exists(name):
            await self.client.create_collection(
                name,
                vectors_config=models.VectorParams(
                    size=space.dimension,
                    distance=getattr(models.Distance, _DISTANCE[space.distance]),
                ),
            )

    async def upsert(
        self,
        ctx: TenantContext,
        space: EmbeddingSpace,
        knowledge_base_id: UUID,
        items: Sequence[tuple[UUID, Sequence[float]]],
    ) -> None:
        for _, vector in items:
            if len(vector) != space.dimension:
                raise InvalidArgument(
                    f"Vector has {len(vector)} dimensions; the space has {space.dimension}."
                )
        if not items:
            return
        points = [
            models.PointStruct(
                id=str(chunk_id),
                vector=list(vector),
                payload={"tenant_id": str(ctx.tenant_id), "kb_id": str(knowledge_base_id)},
            )
            for chunk_id, vector in items
        ]
        await self.client.upsert(self._collection(ctx, space), points=points)

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
        name = self._collection(ctx, space)
        if not await self.client.collection_exists(name):
            return []
        # Publication always filters after the vector search, so ask for more candidates.
        limit = top_k * self.oversample
        result = await self.client.query_points(
            name,
            query=list(vector),
            query_filter=self._filter(ctx, knowledge_base_id),
            limit=max(limit, top_k),
            with_payload=False,
        )
        ids = [UUID(str(point.id)) for point in result.points]
        published: Mapping[UUID, Metadata] = await self.repository.published_chunks(
            ctx, knowledge_base_id, ids
        )
        hits: list[ChunkHit] = []
        for point, chunk_id in zip(result.points, ids, strict=True):
            metadata = published.get(chunk_id)
            if metadata is None or not matches(filters, metadata):
                continue
            score = -point.score if space.distance == Distance.L2 else point.score
            hits.append(ChunkHit(chunk_id, float(score)))
            if len(hits) == top_k:
                break
        return hits

    async def count(
        self, ctx: TenantContext, space: EmbeddingSpace, chunk_ids: Sequence[UUID]
    ) -> int:
        if not chunk_ids:
            return 0
        name = self._collection(ctx, space)
        if not await self.client.collection_exists(name):
            return 0
        flt = models.Filter(must=[models.HasIdCondition(has_id=[str(cid) for cid in chunk_ids])])
        result = await self.client.count(name, count_filter=flt, exact=True)
        return int(result.count)

    async def drop_space(self, ctx: TenantContext, space: EmbeddingSpace) -> None:
        name = self._collection(ctx, space)
        if await self.client.collection_exists(name):
            await self.client.delete_collection(name)


__all__ = ["QdrantVectorIndex"]
