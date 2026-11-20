"""Search result cache (ARCHITECTURE 11.6). Runs with memory and PostgreSQL (see ``world``)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from tests.conftest import World
from vlade_rag.core.application import CreateKnowledgeBase, DeleteDocument, Search, SubmitIngestion
from vlade_rag.core.domain import KnowledgeBaseConfig, RawDocument, ScoredChunk
from vlade_rag.core.domain.kb_config import ChunkingConfig, EmbeddingsConfig

pytestmark = pytest.mark.anyio

PRAZOS = "# Prazos\n\nO prazo de entrega padrão é de cinco dias úteis."
PRAZOS_V2 = "# Prazos\n\nO prazo de entrega padrão passou a ser de dois dias úteis."
GARANTIA = "# Garantia\n\nA garantia dos equipamentos é de um ano."


class CountingFusion:
    """Wraps the fusion strategy. A cache hit skips it, so the counter shows real searches."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.calls = 0

    def fuse(self, lists: Mapping[str, Sequence[ScoredChunk]], top_k: int) -> list[ScoredChunk]:
        self.calls += 1
        return self.inner.fuse(lists, top_k)  # type: ignore[no-any-return]


@pytest.fixture
async def kb(world: World) -> tuple[World, CountingFusion]:
    config = KnowledgeBaseConfig(
        chunking=ChunkingConfig(strategy="markdown", max_tokens=40, overlap_tokens=5),
        embeddings=EmbeddingsConfig(provider="hashing", model="hashing-v1", dimension=64),
    )
    await CreateKnowledgeBase(world.deps).execute(
        world.admin, slug="docs", name="Docs", config=config
    )
    await put(world, "prazos.md", PRAZOS)
    await put(world, "garantia.md", GARANTIA)
    await world.drain_jobs()
    counting = CountingFusion(world.deps.fusion)
    world.deps.fusion = counting  # type: ignore[assignment]
    return world, counting


async def put(world: World, name: str, text: str) -> None:
    await SubmitIngestion(world.deps).execute(
        world.admin,
        knowledge_base="docs",
        raw=RawDocument(filename=name, mime_type="text/markdown", data=text.encode()),
        external_id=name,
    )


async def search(world: World, text: str = "prazo de entrega", **kw: Any) -> list[ScoredChunk]:
    return (
        await Search(world.deps).execute(world.reader, knowledge_base="docs", text=text, **kw)
    ).results


def shape(results: list[ScoredChunk]) -> list[tuple[str, float, int, str]]:
    return [(str(r.chunk.id), r.score, r.rank, r.retriever) for r in results]


async def test_repeated_search_is_served_from_the_cache(kb: tuple[World, CountingFusion]) -> None:
    world, fusion = kb
    first = await search(world)
    assert first and fusion.calls == 1
    second = await search(world)
    assert fusion.calls == 1  # no retrieval the second time
    assert shape(second) == shape(first)
    assert [r.chunk.text for r in second] == [r.chunk.text for r in first]


async def test_a_different_query_or_parameter_is_a_miss(kb: tuple[World, CountingFusion]) -> None:
    world, fusion = kb
    await search(world)
    await search(world, "garantia dos equipamentos")
    await search(world, top_k=3)
    await search(world, filters={"area": "vendas"})
    assert fusion.calls == 4
    await search(world, top_k=3)  # same parameters as the third call
    assert fusion.calls == 4


async def test_publishing_a_new_version_invalidates_the_cache(
    kb: tuple[World, CountingFusion],
) -> None:
    world, fusion = kb
    before = await search(world)
    assert "cinco dias" in " ".join(r.chunk.text for r in before)
    await put(world, "prazos.md", PRAZOS_V2)
    await world.drain_jobs()
    after = await search(world)
    assert fusion.calls == 2  # the epoch changed, so the old entry is not read
    text = " ".join(r.chunk.text for r in after)
    assert "dois dias" in text and "cinco dias" not in text


async def test_deleting_a_document_invalidates_the_cache(kb: tuple[World, CountingFusion]) -> None:
    world, fusion = kb
    first = await search(world, "garantia dos equipamentos")
    assert any("garantia" in r.chunk.text.lower() for r in first)
    doc = first[0].chunk.document_id
    await DeleteDocument(world.deps).execute(
        world.admin, knowledge_base="docs", document_id=doc, confirm=True
    )
    again = await search(world, "garantia dos equipamentos")
    assert fusion.calls == 2
    assert all(r.chunk.document_id != doc for r in again)


async def test_cache_is_not_shared_between_tenants(kb: tuple[World, CountingFusion]) -> None:
    world, fusion = kb
    await search(world)
    other = world.other_admin
    config = KnowledgeBaseConfig(
        embeddings=EmbeddingsConfig(provider="hashing", model="hashing-v1", dimension=64)
    )
    await CreateKnowledgeBase(world.deps).execute(other, slug="docs", name="Docs", config=config)
    result = await Search(world.deps).execute(other, knowledge_base="docs", text="prazo de entrega")
    assert result.results == []  # nothing leaks from the cache of the first tenant
    assert fusion.calls == 2
