"""Contract of the ``VectorIndex`` port: pgvector, memory and Qdrant run the same tests.

pgvector remains the default (ADR-0004). Qdrant runs against an in-process client here, so the
contract needs no service. Every test uses new tenant ids, so it never reads another test's
vectors.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from tests.conftest import World
from vlade_rag.core.application import CreateKnowledgeBase, SubmitIngestion
from vlade_rag.core.domain import EmbeddingSpace, InvalidArgument, KnowledgeBaseConfig, RawDocument
from vlade_rag.core.domain.kb_config import EmbeddingsConfig
from vlade_rag.core.domain.query import Eq
from vlade_rag.core.ports import VectorIndex
from vlade_rag.embeddings.hashing import HashingEmbeddingProvider

pytestmark = pytest.mark.anyio

DIMENSION = 64
DOCS = (
    ("O prazo para responder é de dez dias.", {"lang": "pt"}),
    ("O recurso pode ser pedido em quinze dias.", {"lang": "pt"}),
    ("The appeal can be filed in fifteen days.", {"lang": "en"}),
)
EMBEDDER = HashingEmbeddingProvider(dimension=DIMENSION)


@pytest.fixture(params=["memory", "postgres", "qdrant"])
async def index_world(request: pytest.FixtureRequest, world: World) -> AsyncIterator[World]:
    backend = request.param
    if backend == "memory" and world.backend != "memory":
        pytest.skip("the memory index is already covered by the memory world")
    if backend == "postgres" and world.backend != "postgres":
        pytest.skip("VLADE_TEST_DATABASE_URL is not set")
    if backend == "qdrant":
        pytest.importorskip("qdrant_client")
        from qdrant_client import AsyncQdrantClient

        from vlade_rag.knowledge.qdrant import QdrantVectorIndex

        client = AsyncQdrantClient(location=":memory:")
        world.deps.vector_index = QdrantVectorIndex(client, world.deps.repository)
        try:
            yield world
        finally:
            await client.close()
        return
    yield world


async def _seed(world: World) -> tuple[Any, EmbeddingSpace]:
    config = KnowledgeBaseConfig(
        embeddings=EmbeddingsConfig(provider="h", model="h", dimension=DIMENSION)
    )
    await CreateKnowledgeBase(world.deps).execute(world.admin, slug="kb", name="KB", config=config)
    for i, (text, metadata) in enumerate(DOCS):
        await SubmitIngestion(world.deps).execute(
            world.admin,
            knowledge_base="kb",
            raw=RawDocument(
                f"doc-{i}.md", "text/markdown", text.encode("utf-8"), metadata=metadata
            ),
        )
    await world.drain_jobs()
    kb = await world.deps.repository.get_knowledge_base(world.admin, "kb")
    space = await world.deps.repository.get_embedding_space(
        world.admin, kb.active_embedding_space_id
    )
    return kb, space


async def test_upsert_search_and_count(index_world: World) -> None:
    kb, space = await _seed(index_world)
    index: VectorIndex = index_world.deps.vector_index
    vector = await EMBEDDER.embed_query(DOCS[0][0])
    hits = await index.search(index_world.admin, space, kb.id, vector, 3, None, ef_search=100)
    assert hits
    assert 0.0 <= hits[0].score <= 1.0
    ids = {hit.chunk_id for hit in hits}
    assert await index.count(index_world.admin, space, list(ids)) == len(ids)


async def test_tenant_and_base_isolation(index_world: World) -> None:
    kb, space = await _seed(index_world)
    index: VectorIndex = index_world.deps.vector_index
    vector = await EMBEDDER.embed_query(DOCS[0][0])
    assert await index.search(index_world.admin, space, kb.id, vector, 3, None)
    # A caller of another tenant cannot read the space of the first tenant.
    assert await index.search(index_world.other_admin, space, kb.id, vector, 3, None) == []
    # A different knowledge base of the same tenant cannot read it either.
    other_kb_id = index_world.admin.tenant_id  # a UUID that is not a knowledge base id
    assert await index.search(index_world.admin, space, other_kb_id, vector, 3, None) == []


async def test_publication_and_metadata_filters(index_world: World) -> None:
    kb, space = await _seed(index_world)
    index: VectorIndex = index_world.deps.vector_index
    vector = await EMBEDDER.embed_query("recurso em quinze dias")
    pt = await index.search(index_world.admin, space, kb.id, vector, 10, Eq("lang", "pt"))
    en = await index.search(index_world.admin, space, kb.id, vector, 10, Eq("lang", "en"))
    assert pt and en
    repository = index_world.deps.repository
    pt_meta = await repository.published_chunks(
        index_world.admin, kb.id, [hit.chunk_id for hit in pt]
    )
    en_meta = await repository.published_chunks(
        index_world.admin, kb.id, [hit.chunk_id for hit in en]
    )
    assert all(entry["lang"] == "pt" for entry in pt_meta.values())
    assert all(entry["lang"] == "en" for entry in en_meta.values())


async def test_dimension_validation(index_world: World) -> None:
    kb, space = await _seed(index_world)
    index: VectorIndex = index_world.deps.vector_index
    with pytest.raises(InvalidArgument):
        await index.upsert(index_world.admin, space, kb.id, [(kb.id, [0.0] * (DIMENSION + 1))])
    with pytest.raises(InvalidArgument):
        await index.search(index_world.admin, space, kb.id, [0.0] * (DIMENSION + 1), 3, None)


async def test_drop_space_is_idempotent(index_world: World) -> None:
    _, space = await _seed(index_world)
    index: VectorIndex = index_world.deps.vector_index
    # The port removes the physical index. pgvector keeps the rows and falls back to a scan,
    # while memory and Qdrant remove the vectors, so only idempotency is common to all three.
    await index.drop_space(index_world.admin, space)
    await index.drop_space(index_world.admin, space)
