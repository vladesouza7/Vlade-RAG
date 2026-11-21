"""pgvector VectorIndex, tsvector and trigram LexicalIndex (ADR-0005, ADR-0019)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

import asyncpg

from vlade_rag.core.domain import (
    ChunkHit,
    Distance,
    EmbeddingSpace,
    InvalidArgument,
    MetadataFilter,
    TenantContext,
)
from vlade_rag.knowledge.postgres.db import PostgresDatabase
from vlade_rag.knowledge.postgres.filters import SqlParams, filter_sql
from vlade_rag.knowledge.postgres.repository import text_search_config

_OPERATOR = {Distance.COSINE: "<=>", Distance.L2: "<->", Distance.DOT: "<#>"}


def _vector_type(dimension: int) -> str:
    if not 1 <= dimension <= 4000:
        raise InvalidArgument(f"Unsupported vector dimension {dimension}.")
    return f"vector({dimension})" if dimension <= 2000 else f"halfvec({dimension})"


def _score_sql(distance: Distance, expression: str) -> str:
    if distance == Distance.COSINE:
        return f"1 - ({expression})"
    return f"-({expression})"  # L2: smaller is better; DOT: <#> is the negative inner product


class PgVectorIndex:
    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db

    async def ensure_space(self, ctx: TenantContext, space: EmbeddingSpace) -> None:
        async with self.db.tenant(ctx) as conn:
            await conn.execute(
                "SELECT vlade_ensure_space_index($1, $2, $3)",
                space.id,
                space.dimension,
                space.distance.value,
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
        async with self.db.tenant(ctx) as conn:
            await conn.executemany(
                "INSERT INTO chunk_embeddings (chunk_id, embedding_space_id, tenant_id, "
                "knowledge_base_id, embedding) VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (chunk_id, embedding_space_id) DO UPDATE SET embedding = "
                "EXCLUDED.embedding",
                [
                    (cid, space.id, ctx.tenant_id, knowledge_base_id, list(vec))
                    for cid, vec in items
                ],
            )

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
        vtype = _vector_type(space.dimension)
        distance_expr = f"(e.embedding::{vtype}) {_OPERATOR[space.distance]} $1::{vtype}"
        params = SqlParams(start=5)
        where_filter = filter_sql(filters, params)
        sql = (
            f"SELECT e.chunk_id, {_score_sql(space.distance, distance_expr)} AS score "
            "FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id "
            "WHERE e.embedding_space_id = $2 AND e.knowledge_base_id = $3 AND e.tenant_id = $4 "
            f"AND c.is_published AND {where_filter} "
            f"ORDER BY {distance_expr} LIMIT {int(top_k)}"
        )
        async with self.db.tenant(ctx) as conn:
            await conn.execute(f"SET LOCAL hnsw.ef_search = {max(int(ef_search), int(top_k))}")
            if filters is not None:
                await conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            rows = await conn.fetch(
                sql, list(vector), space.id, knowledge_base_id, ctx.tenant_id, *params.values
            )
        hits = [ChunkHit(r["chunk_id"], float(r["score"])) for r in rows]
        hits.sort(key=lambda h: -h.score)  # relaxed_order may return slightly unordered rows
        return hits

    async def count(
        self, ctx: TenantContext, space: EmbeddingSpace, chunk_ids: Sequence[UUID]
    ) -> int:
        async with self.db.tenant(ctx) as conn:
            value = await conn.fetchval(
                "SELECT count(*) FROM chunk_embeddings WHERE embedding_space_id = $1 "
                "AND chunk_id = ANY($2::uuid[])",
                space.id,
                list(chunk_ids),
            )
        return int(value)


class TsvectorLexicalIndex:
    """Full-text search with ``unaccent`` and stemming. Query terms combine with OR."""

    name = "tsvector"

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db

    async def search(
        self,
        ctx: TenantContext,
        knowledge_base_id: UUID,
        text: str,
        top_k: int,
        filters: MetadataFilter | None,
        language: str,
    ) -> list[ChunkHit]:
        config = text_search_config(language)
        params = SqlParams(start=5)
        where_filter = filter_sql(filters, params)
        sql = (
            "WITH q AS (SELECT to_tsquery('simple', array_to_string(ARRAY("
            "SELECT quote_literal(l) FROM unnest(tsvector_to_array(to_tsvector($1::regconfig, $2)))"
            " AS l), ' | ')) AS query) "
            "SELECT c.id AS chunk_id, ts_rank_cd(c.tsv, q.query) AS score FROM chunks c, q "
            "WHERE q.query::text <> '' AND c.knowledge_base_id = $3 AND c.tenant_id = $4 "
            f"AND c.is_published AND c.tsv @@ q.query AND {where_filter} "
            f"ORDER BY score DESC, c.id LIMIT {int(top_k)}"
        )
        async with self.db.tenant(ctx) as conn:
            rows = await conn.fetch(
                sql, config, text, knowledge_base_id, ctx.tenant_id, *params.values
            )
        return [ChunkHit(r["chunk_id"], float(r["score"])) for r in rows]


FUZZY_THRESHOLD = 0.5  # pg_trgm word similarity from which a query word matches a word of a chunk
FUZZY_MAX_WORDS = 16
_DICTIONARY = {"pt": "portuguese_stem", "en": "english_stem"}
_WORD = re.compile(r"[^\W_]+")


class TrigramLexicalIndex:
    """Fuzzy search with ``pg_trgm`` (ADR-0019). It finds words that are close to the query words,
    so a typo or a missing accent still matches.

    The question is split into words. A stop word is dropped. A chunk matches when one of its
    words has a trigram similarity of 0.5 or more with a query word, and the score of the chunk is
    the sum of the best similarity of each matching query word. The GIN trigram index
    (``chunks_trgm_idx``) is created the first time this adapter runs.
    """

    name = "trigram"

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        self._index_ready = False

    @staticmethod
    def query_words(text: str) -> list[str]:
        words = dict.fromkeys(w for w in _WORD.findall(text.lower()) if len(w) >= 3)
        return list(words)[:FUZZY_MAX_WORDS]

    async def search(
        self,
        ctx: TenantContext,
        knowledge_base_id: UUID,
        text: str,
        top_k: int,
        filters: MetadataFilter | None,
        language: str,
    ) -> list[ChunkHit]:
        words = self.query_words(text)
        if not words:
            return []
        dictionary = _DICTIONARY.get(language.split("-")[0].lower(), "simple")
        params = SqlParams(start=6)
        where_filter = filter_sql(filters, params)
        sql = (
            "WITH w AS (SELECT DISTINCT t AS word FROM unnest($1::text[]) AS t "
            "WHERE cardinality(ts_lexize($2::regdictionary, t)) > 0) "
            "SELECT c.id AS chunk_id, s.score FROM chunks c "
            "CROSS JOIN LATERAL (SELECT sum(sim) AS score FROM "
            "(SELECT word_similarity(w.word, c.text) AS sim FROM w) x WHERE sim >= $5::float8) s "
            "WHERE c.knowledge_base_id = $3 AND c.tenant_id = $4 AND c.is_published "
            "AND s.score IS NOT NULL AND c.text %> ANY (ARRAY(SELECT word FROM w)) "
            f"AND {where_filter} ORDER BY s.score DESC, c.id LIMIT {int(top_k)}"
        )
        async with self.db.tenant(ctx) as conn:
            if not self._index_ready:
                try:
                    await conn.execute("SELECT vlade_ensure_trigram_index()")
                except asyncpg.UndefinedFunctionError:
                    raise InvalidArgument(
                        "The fuzzy retriever needs migration 0002. Run 'vlade-rag db upgrade'."
                    ) from None
                self._index_ready = True
            # The operator %> reads this setting. SET LOCAL ends with the transaction.
            await conn.execute(
                "SELECT set_config('pg_trgm.word_similarity_threshold', $1, true)",
                str(FUZZY_THRESHOLD),
            )
            rows = await conn.fetch(
                sql,
                words,
                dictionary,
                knowledge_base_id,
                ctx.tenant_id,
                FUZZY_THRESHOLD,
                *params.values,
            )
        return [ChunkHit(r["chunk_id"], float(r["score"])) for r in rows]
