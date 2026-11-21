"""The fuzzy retriever and the query transformers inside ``Search`` (roadmap 3.2 and 3.3).

Runs with memory and PostgreSQL (see ``world``).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest

from tests.conftest import World
from vlade_rag.core.application import CreateKnowledgeBase, Search, SubmitIngestion
from vlade_rag.core.domain import (
    ChunkHit,
    InvalidArgument,
    KnowledgeBase,
    KnowledgeBaseConfig,
    MetadataFilter,
    Query,
    RawDocument,
    TenantContext,
)
from vlade_rag.core.domain.kb_config import (
    ChunkingConfig,
    EmbeddingsConfig,
    RetrievalConfig,
)

pytestmark = pytest.mark.anyio

DOCS = {
    "garantia.md": "# Garantia\n\nA garantia dos equipamentos é de um ano a partir da compra.",
    "prazos.md": "# Prazos\n\nO prazo de entrega padrão é de cinco dias úteis para todo o país.",
    "pagamento.md": "# Pagamento\n\nAceitamos boleto, cartão de crédito e Pix, em até doze vezes.",
}


async def make_kb(
    world: World,
    retrievers: tuple[str, ...],
    query_transform: str = "none",
) -> KnowledgeBase:
    config = KnowledgeBaseConfig(
        chunking=ChunkingConfig(strategy="markdown", max_tokens=40, overlap_tokens=5),
        embeddings=EmbeddingsConfig(provider="hashing", model="hashing-v1", dimension=64),
        retrieval=RetrievalConfig(
            retrievers=retrievers,  # type: ignore[arg-type]
            query_transform=query_transform,  # type: ignore[arg-type]
        ),
    )
    created = await CreateKnowledgeBase(world.deps).execute(
        world.admin, slug="vendas", name="Vendas", config=config
    )
    for name, text in DOCS.items():
        await SubmitIngestion(world.deps).execute(
            world.admin,
            knowledge_base="vendas",
            raw=RawDocument(filename=name, mime_type="text/markdown", data=text.encode()),
        )
    await world.drain_jobs()
    return created


async def titles(world: World, text: str, top_k: int = 3) -> list[str]:
    found = await Search(world.deps).execute(
        world.admin, knowledge_base="vendas", text=text, top_k=top_k
    )
    return [r.chunk.document_title for r in found.results]


# ------------------------------------------------------------------ fuzzy (3.3)


async def test_fuzzy_finds_a_chunk_despite_typos(world: World) -> None:
    await make_kb(world, ("fuzzy",))
    # "garatnia" and "equipamnetos" are typos. An exact word search finds nothing for them.
    assert (await titles(world, "garatnia dos equipamnetos"))[0] == "garantia.md"
    assert (await titles(world, "prazo de entrgea"))[0] == "prazos.md"


async def test_the_lexical_retriever_alone_misses_the_same_typos(world: World) -> None:
    await make_kb(world, ("lexical",))
    assert await titles(world, "garatnia equipamnetos") == []


async def test_fuzzy_ignores_a_missing_accent(world: World) -> None:
    await make_kb(world, ("fuzzy",))
    assert (await titles(world, "cartao credito"))[0] == "pagamento.md"


async def test_fuzzy_returns_nothing_for_stop_words_only(world: World) -> None:
    await make_kb(world, ("fuzzy",))
    assert await titles(world, "de da o para com") == []
    assert await titles(world, "xyzzy qwerty") == []  # no word is close to any word of the chunks


async def test_fuzzy_joins_the_other_retrievers(world: World) -> None:
    await make_kb(world, ("dense", "lexical", "fuzzy"))
    found = await Search(world.deps).execute(
        world.admin, knowledge_base="vendas", text="garatnia dos equipamentos", top_k=3
    )
    assert found.results[0].chunk.document_title == "garantia.md"
    assert {r.retriever for r in found.results} == {"fusion"}


async def test_fuzzy_does_not_cross_tenants(world: World) -> None:
    kb = await make_kb(world, ("fuzzy",))
    index = world.deps.lexical_indexes["fuzzy"]
    # The other tenant asks with the identifier of this base: nothing comes back.
    hits = await index.search(world.other_admin, kb.id, "garantia equipamentos", 5, None, "pt")
    assert hits == []
    own = await index.search(world.admin, kb.id, "garantia equipamentos", 5, None, "pt")
    assert own


async def test_fuzzy_applies_the_metadata_filters(world: World) -> None:
    await make_kb(world, ("fuzzy",))
    found = await Search(world.deps).execute(
        world.admin,
        knowledge_base="vendas",
        text="garantia equipamentos",
        top_k=3,
        filters={"inexistente": "x"},
    )
    assert found.results == []


# ------------------------------------------------------------------ query transform (3.2)


class Spy:
    """Wraps a lexical index and records the text of each search."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.name = inner.name
        self.texts: list[str] = []

    async def search(
        self,
        ctx: TenantContext,
        knowledge_base_id: UUID,
        text: str,
        top_k: int,
        filters: MetadataFilter | None,
        language: str,
    ) -> list[ChunkHit]:
        self.texts.append(text)
        hits: list[ChunkHit] = await self.inner.search(
            ctx, knowledge_base_id, text, top_k, filters, language
        )
        return hits


class Stub:
    """A query transformer that returns fixed queries after the original one."""

    def __init__(self, texts: list[str], *, retrievers: tuple[str, ...] | None = None) -> None:
        self.name = "stub"
        self.texts = texts
        self.retrievers = retrievers
        self.calls = 0

    async def transform(self, ctx: TenantContext, kb: KnowledgeBase, query: Query) -> list[Query]:
        self.calls += 1
        return [query, *(replace(query, text=t, retrievers=self.retrievers) for t in self.texts)]


def with_transform(world: World, stub: Any, mode: str = "rewrite") -> Spy:
    spy = Spy(world.deps.lexical_indexes["lexical"])
    world.deps.lexical_indexes = {**world.deps.lexical_indexes, "lexical": spy}  # type: ignore[misc]
    world.deps.query_transformers = {mode: stub}
    return spy


async def test_every_derived_query_runs_on_every_retriever(world: World) -> None:
    await make_kb(world, ("dense", "lexical"), "rewrite")
    stub = Stub(["garantia dos equipamentos"])
    spy = with_transform(world, stub)
    assert (await titles(world, "quanto tempo dura o produto?"))[0] == "garantia.md"
    assert stub.calls == 1
    # The original query and the derived one both reached the lexical retriever.
    assert spy.texts == ["quanto tempo dura o produto?", "garantia dos equipamentos"]


async def test_a_query_can_be_limited_to_some_retrievers(world: World) -> None:
    await make_kb(world, ("dense", "lexical"), "hyde")
    stub = Stub(["texto hipotético sobre garantia"], retrievers=("dense",))
    spy = with_transform(world, stub, "hyde")
    await titles(world, "garantia")
    assert spy.texts == ["garantia"]  # the derived query skipped the lexical retriever


async def test_the_original_query_always_runs_first(world: World) -> None:
    await make_kb(world, ("dense", "lexical"), "rewrite")

    class Faulty:
        name = "faulty"

        async def transform(
            self, ctx: TenantContext, kb: KnowledgeBase, query: Query
        ) -> list[Query]:
            return [replace(query, text="outra coisa")]  # forgets the original

    spy = with_transform(world, Faulty())
    await titles(world, "garantia dos equipamentos")
    assert spy.texts == ["garantia dos equipamentos", "outra coisa"]


async def test_a_transform_that_is_not_configured_is_refused(world: World) -> None:
    await make_kb(world, ("dense", "lexical"), "hyde")
    world.deps.query_transformers = {}
    with pytest.raises(InvalidArgument, match="Query transform 'hyde' is not configured"):
        await titles(world, "garantia")


async def test_without_a_transform_the_transformers_are_not_called(world: World) -> None:
    await make_kb(world, ("dense", "lexical"), "none")
    stub = Stub(["x"])
    spy = with_transform(world, stub)
    await titles(world, "garantia")
    assert stub.calls == 0 and spy.texts == ["garantia"]


async def test_the_result_cache_does_not_mix_transforms(world: World) -> None:
    kb = await make_kb(world, ("dense", "lexical"), "none")
    plain = Search._cache_key(kb, Query("q", kb.id), 3, False)
    changed = replace(
        kb,
        config=kb.config.model_copy(
            update={
                "retrieval": kb.config.retrieval.model_copy(update={"query_transform": "rewrite"})
            }
        ),
    )
    assert Search._cache_key(changed, Query("q", kb.id), 3, False) != plain
