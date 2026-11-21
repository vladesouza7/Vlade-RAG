"""The bm25 retriever (roadmap 3.4, ADR-0022).

``bm25_world`` runs with memory and with PostgreSQL plus ``pg_search``
(``VLADE_TEST_BM25_DATABASE_URL``). ``world`` checks the message on a server without ``pg_search``.
"""

from __future__ import annotations

import pytest

from tests.conftest import World
from vlade_rag.core.application import (
    CreateKnowledgeBase,
    DeleteDocument,
    Search,
    SubmitIngestion,
)
from vlade_rag.core.domain import InvalidArgument, KnowledgeBase, KnowledgeBaseConfig, RawDocument
from vlade_rag.core.domain.kb_config import ChunkingConfig, EmbeddingsConfig, RetrievalConfig
from vlade_rag.core.domain.query import And, Eq, Exists, In, Or
from vlade_rag.knowledge.postgres.filters import filter_json
from vlade_rag.knowledge.postgres.indexes import bm25_field

pytestmark = pytest.mark.anyio

DOCS_PT = {
    "garantia.md": (
        "# Garantia\n\nA garantia dos equipamentos é de um ano a partir da compra.",
        {"area": "pos-venda", "nivel": 1},
    ),
    "prazos.md": (
        "# Prazos\n\nO prazo de entrega padrão é de cinco dias úteis para todo o país.",
        {"area": "logistica", "nivel": 2},
    ),
    "pagamento.md": (
        "# Pagamento\n\nAceitamos boleto, cartão de crédito e Pix, em até doze vezes.",
        {"area": "financeiro"},
    ),
}
DOCS_EN = {
    "shoes.md": ("# Shoes\n\nOur running shoes are light and they last for years.", {}),
    "returns.md": ("# Returns\n\nYou can return any product within thirty days.", {}),
}


async def make_kb(
    world: World,
    retrievers: tuple[str, ...] = ("bm25",),
    *,
    slug: str = "vendas",
    language: str = "pt",
    ctx_name: str = "admin",
) -> KnowledgeBase:
    ctx = getattr(world, ctx_name)
    config = KnowledgeBaseConfig(
        language=language,
        chunking=ChunkingConfig(strategy="markdown", max_tokens=40, overlap_tokens=5),
        embeddings=EmbeddingsConfig(provider="hashing", model="hashing-v1", dimension=64),
        retrieval=RetrievalConfig(retrievers=retrievers),  # type: ignore[arg-type]
    )
    created = await CreateKnowledgeBase(world.deps).execute(
        ctx, slug=slug, name=slug, config=config
    )
    for name, (text, metadata) in (DOCS_PT if language == "pt" else DOCS_EN).items():
        await SubmitIngestion(world.deps).execute(
            ctx,
            knowledge_base=slug,
            raw=RawDocument(
                filename=name, mime_type="text/markdown", data=text.encode(), metadata=metadata
            ),
        )
    await world.drain_jobs()
    return created


async def titles(
    world: World, text: str, *, slug: str = "vendas", filters: dict | None = None
) -> list[str]:
    found = await Search(world.deps).execute(
        world.admin, knowledge_base=slug, text=text, top_k=3, filters=filters
    )
    return [r.chunk.document_title for r in found.results]


# ------------------------------------------------------------------ ranking


async def test_bm25_ranks_the_chunk_with_the_query_words_first(bm25_world: World) -> None:
    await make_kb(bm25_world)
    assert (await titles(bm25_world, "garantia dos equipamentos"))[0] == "garantia.md"
    assert (await titles(bm25_world, "prazo de entrega"))[0] == "prazos.md"


async def test_bm25_ignores_accents_and_word_endings(bm25_world: World) -> None:
    await make_kb(bm25_world)
    # "credito" has no accent and "cartoes" is a plural. Stemming and folding still match.
    assert (await titles(bm25_world, "cartoes de credito"))[0] == "pagamento.md"


def needs_pg_search(world: World) -> None:
    if world.backend == "memory":
        pytest.skip("the memory index has no stemmer and no stop words")


async def test_bm25_uses_the_language_of_the_base(bm25_world: World) -> None:
    needs_pg_search(bm25_world)
    await make_kb(bm25_world, slug="store", language="en")
    # "run" matches "running" only with the English stemmer.
    assert (await titles(bm25_world, "run", slug="store"))[0] == "shoes.md"
    assert (await titles(bm25_world, "returning products", slug="store"))[0] == "returns.md"


async def test_bm25_returns_nothing_for_stop_words_or_unknown_words(bm25_world: World) -> None:
    needs_pg_search(bm25_world)
    await make_kb(bm25_world)
    assert await titles(bm25_world, "de da o para com") == []
    assert await titles(bm25_world, "xyzzy qwerty") == []


async def test_query_syntax_is_plain_text(bm25_world: World) -> None:
    await make_kb(bm25_world)
    # Quotes, operators and SQL do not change the search: the words are searched as text.
    assert (await titles(bm25_world, 'garantia" OR 1=1 -- (prazo) AND *'))[0] in {
        "garantia.md",
        "prazos.md",
    }
    assert await titles(bm25_world, "'; DROP TABLE chunks; --") == []


async def test_bm25_joins_the_other_retrievers(bm25_world: World) -> None:
    await make_kb(bm25_world, ("dense", "bm25"))
    found = await Search(bm25_world.deps).execute(
        bm25_world.admin, knowledge_base="vendas", text="garantia dos equipamentos", top_k=3
    )
    assert found.results[0].chunk.document_title == "garantia.md"
    assert {r.retriever for r in found.results} == {"fusion"}


# ------------------------------------------------------------------ filters and isolation


async def test_bm25_applies_the_metadata_filters(bm25_world: World) -> None:
    await make_kb(bm25_world)
    text = "garantia prazo pagamento"
    assert await titles(bm25_world, text, filters={"area": "logistica"}) == ["prazos.md"]
    either = {"area": {"in": ["logistica", "financeiro"]}}
    assert set(await titles(bm25_world, text, filters=either)) == {"prazos.md", "pagamento.md"}
    assert await titles(bm25_world, text, filters={"area": "inexistente"}) == []


async def test_bm25_does_not_cross_tenants(bm25_world: World) -> None:
    kb = await make_kb(bm25_world)
    other = await make_kb(bm25_world, slug="vendas", ctx_name="other_admin")
    index = bm25_world.deps.lexical_indexes["bm25"]
    # The other tenant asks with the identifier of this base: nothing comes back.
    assert await index.search(bm25_world.other_admin, kb.id, "garantia", 5, None, "pt") == []
    assert await index.search(bm25_world.admin, other.id, "garantia", 5, None, "pt") == []
    own = await index.search(bm25_world.admin, kb.id, "garantia", 5, None, "pt")
    assert len(own) == 1


async def test_a_deleted_document_leaves_the_results(bm25_world: World) -> None:
    await make_kb(bm25_world)
    found = await Search(bm25_world.deps).execute(
        bm25_world.admin, knowledge_base="vendas", text="garantia equipamentos", top_k=3
    )
    document_id = found.results[0].chunk.document_id
    await DeleteDocument(bm25_world.deps).execute(
        bm25_world.admin, knowledge_base="vendas", document_id=document_id, confirm=True
    )
    assert await titles(bm25_world, "garantia equipamentos") == []


# ------------------------------------------------------------------ without pg_search


async def test_without_pg_search_the_message_names_the_image(world: World) -> None:
    if world.backend == "memory":
        pytest.skip("the memory backend has no pg_search requirement")
    async with world.extra["db"].tenant(world.admin) as conn:
        available = await conn.fetchval(
            "SELECT count(*) FROM pg_available_extensions WHERE name = 'pg_search'"
        )
    if available:
        pytest.skip("this server has pg_search")
    await make_kb(world, ("bm25",))
    with pytest.raises(InvalidArgument, match="vlade-postgres-bm25"):
        await titles(world, "garantia")


# ------------------------------------------------------------------ helpers


def test_the_filter_json_mirrors_the_filter_types() -> None:
    flt = And((Eq("a", 1), Or((In("b", ("x", "y")), Exists("c")))))
    assert filter_json(flt) == {
        "op": "and",
        "items": [
            {"op": "eq", "key": "a", "value": 1},
            {
                "op": "or",
                "items": [
                    {"op": "in", "key": "b", "values": ["x", "y"]},
                    {"op": "exists", "key": "c"},
                ],
            },
        ],
    }
    assert filter_json(None) is None


@pytest.mark.parametrize(
    ("language", "field"),
    [
        ("pt", "text_pt"),
        ("pt-BR", "text_pt"),
        ("en", "text_en"),
        ("EN-us", "text_en"),
        ("es", "text_simple"),
    ],
)
def test_the_bm25_field_follows_the_language(language: str, field: str) -> None:
    assert bm25_field(language) == field
