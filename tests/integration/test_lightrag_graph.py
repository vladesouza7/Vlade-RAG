"""LightRAG adapter against PostgreSQL, without any model (phase 6, ADR-0032).

The extraction LLM is fake and deterministic: capitalized names become entities and consecutive
names become relations, in the LightRAG delimiter format. It also answers the keyword prompt of
each query. The embeddings use feature hashing. Needs the ``graph`` extra and
``VLADE_TEST_DATABASE_URL``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
from collections.abc import AsyncIterator, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import pytest

pytest.importorskip("lightrag")

from vlade_rag.core.config.settings import GraphSettings
from vlade_rag.core.domain import (
    Chunk,
    Generation,
    GenerationDelta,
    GenerationParams,
    KnowledgeBase,
    KnowledgeBaseConfig,
    Message,
    Role,
    TenantContext,
    uuid7,
)
from vlade_rag.embeddings.hashing import HashingEmbeddingProvider
from vlade_rag.knowledge.graph.lightrag import LightRAGGraphIndex

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

TUPLE = "<|#|>"
_NAME = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]+(?:\s[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]+)*")
_STOP = {"O", "A", "Os", "As", "Em", "No", "Na", "Para", "Segundo"}


def _names(text: str) -> list[str]:
    found: list[str] = []
    for match in _NAME.finditer(text):
        name = match.group(0).strip()
        if name not in _STOP and len(name) > 2 and name not in found:
            found.append(name)
    return found[:8]


class FakeGraphLLM:
    name = "fake-graph"

    async def generate(self, messages: Sequence[Message], params: GenerationParams) -> Generation:
        prompt = "\n".join(m.content for m in messages)
        if "User Query:" in prompt:
            query = prompt.split("User Query:")[-1].split("\n")[0]
            names = _names(query)
            text = json.dumps({"high_level_keywords": names, "low_level_keywords": names})
        elif "---Input Text---" in prompt:
            names = _names(prompt.split("---Input Text---")[-1])
            lines = [f"entity{TUPLE}{n}{TUPLE}concept{TUPLE}{n} aparece no texto." for n in names]
            lines += [
                f"relation{TUPLE}{a}{TUPLE}{b}{TUPLE}relacionado{TUPLE}{a} se liga a {b}."
                for a, b in pairwise(names)
            ]
            text = "\n".join(lines) + "\n<|COMPLETE|>"
        else:
            text = "Resumo."
        return Generation(text=text, model="fake")

    async def stream(
        self, messages: Sequence[Message], params: GenerationParams
    ) -> AsyncIterator[GenerationDelta]:
        yield GenerationDelta((await self.generate(messages, params)).text)


@pytest.fixture(scope="module")
def graph_url() -> Iterator[str]:
    url = os.environ.get("VLADE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("VLADE_TEST_DATABASE_URL is not set")
    import asyncpg

    database = f"vlade_graph_test_{secrets.token_hex(4)}"
    parts = urlsplit(url)
    graph = urlunsplit((parts.scheme, parts.netloc, f"/{database}", "", ""))

    async def setup() -> None:
        conn = await asyncpg.connect(url)
        await conn.execute(f'CREATE DATABASE "{database}"')
        await conn.close()
        conn = await asyncpg.connect(graph)
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.close()

    async def teardown() -> None:
        conn = await asyncpg.connect(url)
        await conn.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        await conn.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, setup()).result()
    yield graph
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, teardown()).result()


@pytest.fixture
async def graph(graph_url: str, tmp_path: Path) -> AsyncIterator[LightRAGGraphIndex]:
    llm = FakeGraphLLM()
    embedder = HashingEmbeddingProvider(dimension=64)
    index = LightRAGGraphIndex(
        GraphSettings(database_url=graph_url, working_dir=str(tmp_path)),  # type: ignore[arg-type]
        llms=lambda cfg: llm,
        embeddings=lambda cfg: embedder,
    )
    yield index
    await index.aclose()


def _ctx() -> TenantContext:
    tenant = uuid7()
    return TenantContext(tenant, tenant, frozenset({Role.ADMIN}), "library")


def _kb(ctx: TenantContext) -> KnowledgeBase:
    config = KnowledgeBaseConfig.model_validate(
        {
            "embeddings": {"provider": "hashing", "model": "hashing-v1", "dimension": 64},
            "graph": {"enabled": True, "provider": "fake", "model": "fake"},
        }
    )
    return KnowledgeBase(uuid7(), ctx.tenant_id, "teologia", "Teologia", config, uuid7())


def _chunks(
    kb: KnowledgeBase, document_id: UUID, version_id: UUID, texts: list[str]
) -> list[Chunk]:
    return [
        Chunk(
            id=uuid7(),
            tenant_id=kb.tenant_id,
            knowledge_base_id=kb.id,
            document_id=document_id,
            document_version_id=version_id,
            ordinal=i,
            text=text,
            token_count=len(text.split()),
            start_offset=0,
            end_offset=len(text),
        )
        for i, text in enumerate(texts)
    ]


GRUDEM = "Wayne Grudem defende a Teologia da Aliança na Teologia Sistemática."
RYRIE = "Charles Ryrie defende o Dispensacionalismo e distingue Israel e Igreja."


async def test_index_search_replace_and_delete(graph: LightRAGGraphIndex) -> None:
    ctx = _ctx()
    kb = _kb(ctx)
    doc, v1 = uuid7(), uuid7()
    chunks = _chunks(kb, doc, v1, [GRUDEM, RYRIE])
    assert await graph.index_document(ctx, kb, doc, v1, chunks) == 2

    result = await graph.search(ctx, kb, "Wayne Grudem e Charles Ryrie", mode="hybrid", top_k=10)
    names = {e.name for e in result.entities}
    assert {"Wayne Grudem", "Charles Ryrie"} & names
    assert result.relations
    assert {h.chunk_id for h in result.chunk_hits} <= {c.id for c in chunks}
    assert result.chunk_hits  # LightRAG chunks map back to Vlade-RAG chunk ids

    v2 = uuid7()
    new_chunks = _chunks(kb, doc, v2, [GRUDEM.replace("Wayne Grudem", "Millard Erickson")])
    await graph.index_document(ctx, kb, doc, v2, new_chunks)
    after = await graph.search(ctx, kb, "Millard Erickson", mode="hybrid", top_k=10)
    assert {h.chunk_id for h in after.chunk_hits} <= {c.id for c in new_chunks}

    assert await graph.delete_document(ctx, kb, doc) == 1
    empty = await graph.search(ctx, kb, "Millard Erickson", mode="hybrid", top_k=10)
    assert empty.entities == () and empty.chunk_hits == ()


async def test_workspaces_are_isolated(graph: LightRAGGraphIndex) -> None:
    ctx_a, ctx_b = _ctx(), _ctx()
    kb_a, kb_b = _kb(ctx_a), _kb(ctx_b)
    doc = uuid7()
    chunks = _chunks(kb_a, doc, uuid7(), [GRUDEM])
    await graph.index_document(ctx_a, kb_a, doc, chunks[0].document_version_id, chunks)
    leaked = await graph.search(ctx_b, kb_b, "Wayne Grudem", mode="hybrid", top_k=10)
    assert leaked.entities == () and leaked.chunk_hits == ()
    await graph.ping()
