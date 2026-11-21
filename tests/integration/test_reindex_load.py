"""Concurrent reindex under load (roadmap 4.4 acceptance, ADR-0027).

Searches, ingestions and a reindex run at the same time. Every search checks that the chunks it
received have vectors in the space used by that search, so no result can come from a retired space.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.conftest import World
from vlade_rag.core.application import (
    CreateKnowledgeBase,
    ReindexKnowledgeBase,
    RunIngestionJob,
    Search,
    SubmitIngestion,
)
from vlade_rag.core.domain import JobStatus, KnowledgeBaseConfig, RawDocument
from vlade_rag.core.domain.kb_config import ChunkingConfig, EmbeddingsConfig, RetrievalConfig

pytestmark = pytest.mark.anyio

SEARCHES = 25
INGESTIONS = 6


async def _load(world: World, mode: str) -> dict[str, int]:
    config = KnowledgeBaseConfig(
        chunking=ChunkingConfig(strategy="markdown", max_tokens=200, overlap_tokens=10),
        embeddings=EmbeddingsConfig(provider="hashing", model="hashing-v1", dimension=64),
        retrieval=RetrievalConfig(retrievers=("dense",)),
    )
    await CreateKnowledgeBase(world.deps).execute(
        world.admin, slug="carga", name="Carga", config=config
    )
    for number in range(3):
        await SubmitIngestion(world.deps).execute(
            world.admin,
            knowledge_base="carga",
            raw=RawDocument(
                filename=f"base-{number}.md",
                mime_type="text/markdown",
                data=f"# Base {number}\n\nGarantia dos equipamentos por um ano.".encode(),
            ),
            external_id=f"base-{number}.md",
        )
    await world.drain_jobs()

    index = world.deps.vector_index
    real_search = index.search
    checked: list[int] = []

    async def search_and_check(*args: Any, **kwargs: Any) -> Any:
        space = args[1]  # (ctx, space, kb_id, vector, top_k, filters)
        hits = await real_search(*args, **kwargs)
        count = await index.count(args[0], space, [hit.chunk_id for hit in hits])
        if count != len(hits):
            raise AssertionError(f"A search mixed embedding spaces: {count}/{len(hits)} vectors")
        checked.append(len(hits))
        return hits

    index.search = search_and_check  # type: ignore[method-assign]
    submitted: list[Any] = []
    try:
        options = (
            {"embeddings": {"model": "hashing-v2"}}
            if mode == "embeddings"
            else {"chunking": {"max_tokens": 16, "overlap_tokens": 2}}
        )
        queued = await ReindexKnowledgeBase(world.deps).execute(
            world.admin,
            knowledge_base="carga",
            mode=mode,
            confirm=True,
            **options,
        )

        async def searches() -> None:
            use_case = Search(world.deps)
            for number in range(SEARCHES):
                # A different query avoids the result cache, so every search reaches the index.
                await use_case.execute(
                    world.admin,
                    knowledge_base="carga",
                    text=f"garantia dos equipamentos {number}",
                    top_k=3,
                )

        async def ingestions() -> None:
            use_case = SubmitIngestion(world.deps)
            for number in range(INGESTIONS):
                result = await use_case.execute(
                    world.admin,
                    knowledge_base="carga",
                    raw=RawDocument(
                        filename=f"novo-{number}.md",
                        mime_type="text/markdown",
                        data=f"# Novo {number}\n\nPrazo de entrega de cinco dias.".encode(),
                    ),
                    external_id=f"novo-{number}.md",
                )
                submitted.append(result.job)

        async def worker() -> None:
            runner = RunIngestionJob(world.deps)
            while (claimed := await world.job_queue.claim("load-worker", 60)) is not None:
                await runner.execute(claimed)
                await asyncio.sleep(0)

        await asyncio.gather(worker(), searches(), ingestions())
    finally:
        index.search = real_search  # type: ignore[method-assign]

    job = await world.deps.job_queue.get(world.admin, queued.job.id)
    assert job.status == JobStatus.SUCCEEDED, job.error
    for ingest_job in submitted:
        done = await world.deps.job_queue.get(world.admin, ingest_job.id)
        assert done.status == JobStatus.SUCCEEDED, done.error

    kb = await world.deps.repository.get_knowledge_base(world.admin, "carga")
    space = await world.deps.repository.get_embedding_space(
        world.admin, kb.active_embedding_space_id
    )
    chunks = await world.deps.repository.list_published_chunks(
        world.admin, kb.id, after=None, limit=10_000
    )
    if mode == "embeddings":
        assert space.model == "hashing-v2"
    else:
        assert kb.config.chunking.max_tokens == 16
        assert space.model == "hashing-v1"
    assert await index.count(world.admin, space, [c.id for c in chunks]) == len(chunks)
    return {"searches": len(checked), "ingestions": len(submitted), "chunks": len(chunks)}


@pytest.mark.parametrize("mode", ["embeddings", "full"])
async def test_searches_and_ingestions_survive_a_reindex(world: World, mode: str) -> None:
    report = await _load(world, mode)
    assert report["searches"] == SEARCHES
    assert report["ingestions"] == INGESTIONS
    assert report["chunks"] > 0
