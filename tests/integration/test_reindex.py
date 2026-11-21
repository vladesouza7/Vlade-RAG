"""Reindex without downtime (roadmap 4.2, ARCHITECTURE section 13, ADR-0027).

Runs with memory and PostgreSQL (see ``world``). The test embedder has 64 dimensions, so the
new model keeps the dimension and changes the model name.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from tests.conftest import World
from vlade_rag.core.application import (
    CreateKnowledgeBase,
    ReindexKnowledgeBase,
    Search,
    SubmitIngestion,
)
from vlade_rag.core.domain import (
    Conflict,
    EmbeddingSpaceChanged,
    InvalidArgument,
    JobStatus,
    KnowledgeBase,
    KnowledgeBaseConfig,
    MissingVectors,
    PermissionDenied,
    RawDocument,
    SpaceStatus,
)
from vlade_rag.core.domain.kb_config import ChunkingConfig, EmbeddingsConfig, RetrievalConfig

pytestmark = pytest.mark.anyio

DOCS = {
    "garantia.md": "# Garantia\n\nA garantia dos equipamentos é de um ano a partir da compra. "
    "Ela cobre defeitos de fabricação e não cobre mau uso.",
    "prazos.md": "# Prazos\n\nO prazo de entrega padrão é de cinco dias úteis para todo o país. "
    "Regiões remotas podem levar até dez dias úteis.",
    "pagamento.md": "# Pagamento\n\nAceitamos boleto, cartão de crédito e Pix, em até doze vezes.",
}
NEW_MODEL = {"model": "hashing-v2"}


async def make_kb(world: World) -> KnowledgeBase:
    config = KnowledgeBaseConfig(
        chunking=ChunkingConfig(strategy="markdown", max_tokens=200, overlap_tokens=10),
        embeddings=EmbeddingsConfig(provider="hashing", model="hashing-v1", dimension=64),
        retrieval=RetrievalConfig(retrievers=("dense",)),
    )
    await CreateKnowledgeBase(world.deps).execute(
        world.admin, slug="vendas", name="Vendas", config=config
    )
    for name, text in DOCS.items():
        await submit(world, name, text)
    await world.drain_jobs()
    return await kb_now(world)


async def submit(world: World, name: str, text: str) -> Any:
    return await SubmitIngestion(world.deps).execute(
        world.admin,
        knowledge_base="vendas",
        raw=RawDocument(filename=name, mime_type="text/markdown", data=text.encode()),
        external_id=name,
    )


async def kb_now(world: World) -> KnowledgeBase:
    return await world.deps.repository.get_knowledge_base(world.admin, "vendas")


async def reindex(world: World, mode: str = "embeddings", **kw: Any) -> Any:
    return await ReindexKnowledgeBase(world.deps).execute(
        world.admin, knowledge_base="vendas", mode=mode, **kw
    )


async def published(world: World, kb: KnowledgeBase) -> list[Any]:
    return await world.deps.repository.list_published_chunks(
        world.admin, kb.id, after=None, limit=10_000
    )


async def titles(world: World, text: str) -> list[str]:
    found = await Search(world.deps).execute(
        world.admin, knowledge_base="vendas", text=text, top_k=3
    )
    return [r.chunk.document_title for r in found.results]


# ------------------------------------------------------------------ request


async def test_the_preview_changes_nothing(world: World) -> None:
    before = await make_kb(world)
    result = await reindex(world, embeddings=NEW_MODEL)
    assert not result.executed and result.job is None
    p = result.preview
    assert (p.documents, p.mode, p.embeddings.model) == (3, "embeddings", "hashing-v2")
    assert p.chunks == len(await published(world, before)) > 0
    assert p.estimated_embedding_calls == 1  # every chunk fits in one batch of 32
    after = await kb_now(world)
    assert after.active_embedding_space_id == before.active_embedding_space_id
    assert after.config.embeddings.model == "hashing-v1"


async def test_bad_requests_are_refused(world: World) -> None:
    await make_kb(world)
    with pytest.raises(InvalidArgument, match="mode"):
        await reindex(world, mode="partial")
    with pytest.raises(InvalidArgument, match="embedding model"):
        await reindex(world, mode="full", embeddings=NEW_MODEL)
    with pytest.raises(InvalidArgument, match="chunking"):
        await reindex(world, embeddings=NEW_MODEL, chunking={"max_tokens": 100})
    with pytest.raises(InvalidArgument, match="embeddings configuration"):
        await reindex(world, embeddings={"dimension": 0})
    with pytest.raises(PermissionDenied):
        await ReindexKnowledgeBase(world.deps).execute(
            world.reader, knowledge_base="vendas", mode="embeddings", confirm=True
        )


async def test_a_second_reindex_is_a_conflict(world: World) -> None:
    await make_kb(world)
    first = await reindex(world, embeddings=NEW_MODEL, confirm=True)
    assert first.executed and first.job.status == JobStatus.PENDING
    with pytest.raises(Conflict, match="already running"):
        await reindex(world, mode="full", chunking={"max_tokens": 100}, confirm=True)
    await world.drain_jobs()
    second = await reindex(world, embeddings={"model": "hashing-v3"}, confirm=True)
    assert second.executed  # the first one finished


# ------------------------------------------------------------------ embeddings mode


async def test_the_embeddings_mode_switches_to_a_new_space(world: World) -> None:
    before = await make_kb(world)
    old_space = before.active_embedding_space_id
    result = await reindex(world, embeddings=NEW_MODEL, confirm=True)
    assert await titles(world, "garantia dos equipamentos")  # the old space still answers
    assert await world.drain_jobs() == 1

    job = await world.deps.job_queue.get(world.admin, result.job.id)
    assert job.status == JobStatus.SUCCEEDED, job.error
    after = await kb_now(world)
    assert after.active_embedding_space_id != old_space
    assert after.config.embeddings.model == "hashing-v2"
    assert after.epoch > before.epoch  # cached searches of the old space are not read again
    repo = world.deps.repository
    new = await repo.get_embedding_space(world.admin, after.active_embedding_space_id)
    old = await repo.get_embedding_space(world.admin, old_space)
    assert (new.status, new.model, old.status) == (
        SpaceStatus.ACTIVE,
        "hashing-v2",
        SpaceStatus.RETIRED,
    )
    chunks = await published(world, after)
    assert await world.deps.vector_index.count(world.admin, new, [c.id for c in chunks]) == len(
        chunks
    )
    assert job.result["chunks_embedded"] == len(chunks)
    assert job.result["retired_space_id"] == str(old_space)
    assert (await titles(world, "garantia dos equipamentos"))[0] == "garantia.md"


async def test_a_wrong_dimension_fails_the_job_and_keeps_the_base(world: World) -> None:
    before = await make_kb(world)
    result = await reindex(world, embeddings={"dimension": 32}, confirm=True)
    await world.drain_jobs()
    job = await world.deps.job_queue.get(world.admin, result.job.id)
    assert job.status == JobStatus.FAILED
    assert "dimensions" in job.error["message"]
    after = await kb_now(world)
    assert after.active_embedding_space_id == before.active_embedding_space_id
    assert after.config.embeddings.dimension == 64


async def test_a_document_published_during_the_build_gets_a_vector(world: World) -> None:
    """The switch finds the chunk without a vector, embeds it and switches again."""
    await make_kb(world)
    repo = world.deps.repository
    real = repo.activate_embedding_space
    calls = {"n": 0}

    async def activate_after_a_new_document(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            # A document published in the old space after the catch-up pass.
            await submit(world, "devolucao.md", "# Devolução\n\nA devolução leva sete dias.")
            await world.drain_jobs()
        return await real(*args, **kwargs)

    repo.activate_embedding_space = activate_after_a_new_document  # type: ignore[method-assign]
    try:
        result = await reindex(world, embeddings=NEW_MODEL, confirm=True)
        await world.drain_jobs()
    finally:
        repo.activate_embedding_space = real  # type: ignore[method-assign]
    job = await world.deps.job_queue.get(world.admin, result.job.id)
    assert job.status == JobStatus.SUCCEEDED, job.error
    assert calls["n"] == 2  # the first switch found a chunk without a vector
    kb = await kb_now(world)
    space = await repo.get_embedding_space(world.admin, kb.active_embedding_space_id)
    chunks = await published(world, kb)
    assert {c.document_title for c in chunks} >= {"devolucao.md"}
    assert await world.deps.vector_index.count(world.admin, space, [c.id for c in chunks]) == len(
        chunks
    )


async def test_the_switch_refuses_a_space_with_missing_vectors(world: World) -> None:
    kb = await make_kb(world)
    repo = world.deps.repository
    space = await repo.create_embedding_space(
        world.admin, EmbeddingsConfig(provider="hashing", model="hashing-v2", dimension=64)
    )
    assert space.status == SpaceStatus.BUILDING
    await world.deps.vector_index.ensure_space(world.admin, space)
    with pytest.raises(MissingVectors):
        await repo.activate_embedding_space(world.admin, kb.id, space.id, kb.config.embeddings)
    assert (await kb_now(world)).active_embedding_space_id == kb.active_embedding_space_id


async def test_an_ingestion_that_publishes_after_the_switch_embeds_again(world: World) -> None:
    """The vectors of the job went to the old space; the publication sees the new one."""
    await make_kb(world)
    index, repo = world.deps.vector_index, world.deps.repository
    real_upsert = index.upsert
    switched = {"done": False, "job_writes_after": 0}

    async def upsert_then_switch(ctx: Any, space: Any, kb_id: Any, items: Any) -> Any:
        await real_upsert(ctx, space, kb_id, items)
        if switched["done"] and space.model == "hashing-v2":
            switched["job_writes_after"] += 1  # the job embeds again, in the new space
        if not switched["done"] and space.model == "hashing-v1":
            switched["done"] = True
            # A reindex switches the base while this ingestion job runs.
            config = EmbeddingsConfig(provider="hashing", model="hashing-v2", dimension=64)
            new = await repo.create_embedding_space(ctx, config)
            await index.ensure_space(ctx, new)
            chunks = await repo.list_published_chunks(ctx, kb_id, after=None, limit=10_000)
            embedder = world.deps.embeddings(config)
            vectors = await embedder.embed_documents([c.text for c in chunks])
            pairs = list(zip((c.id for c in chunks), vectors, strict=True))
            await real_upsert(ctx, new, kb_id, pairs)
            await repo.activate_embedding_space(ctx, kb_id, new.id, config)

    index.upsert = upsert_then_switch  # type: ignore[method-assign]
    try:
        text = "# Devolução\n\nA devolução leva sete dias."
        submitted = await submit(world, "devolucao.md", text)
        await world.drain_jobs()
    finally:
        index.upsert = real_upsert  # type: ignore[method-assign]
    job = await world.deps.job_queue.get(world.admin, submitted.job.id)
    assert job.status == JobStatus.SUCCEEDED, job.error
    assert switched["done"] and switched["job_writes_after"] == 1
    kb = await kb_now(world)
    space = await repo.get_embedding_space(world.admin, kb.active_embedding_space_id)
    chunks = await published(world, kb)
    assert await index.count(world.admin, space, [c.id for c in chunks]) == len(chunks)


async def test_publishing_with_an_old_space_is_refused(world: World) -> None:
    kb = await make_kb(world)
    other = await world.deps.repository.create_embedding_space(world.admin, kb.config.embeddings)
    submitted = await submit(world, "novo.md", "# Novo\n\nTexto novo.")
    version_id = UUID(submitted.job.input["version_id"])
    with pytest.raises(EmbeddingSpaceChanged):
        await world.deps.repository.publish_version(
            world.admin, version_id, embedding_space_id=other.id
        )


# ------------------------------------------------------------------ full mode


async def test_the_full_mode_reprocesses_every_document(world: World) -> None:
    before = await make_kb(world)
    old_chunks = await published(world, before)
    result = await reindex(world, mode="full", chunking={"max_tokens": 16, "overlap_tokens": 2})
    assert result.preview.chunking.max_tokens == 16 and not result.executed
    result = await reindex(
        world, mode="full", chunking={"max_tokens": 16, "overlap_tokens": 2}, confirm=True
    )
    assert await world.drain_jobs() == 1 + len(DOCS)  # the reindex job and one job per document

    job = await world.deps.job_queue.get(world.admin, result.job.id)
    assert job.status == JobStatus.SUCCEEDED, job.error
    assert job.result == {"mode": "full", "documents": 3, "ingestion_jobs": 3}
    after = await kb_now(world)
    assert after.config.chunking.max_tokens == 16
    assert after.active_embedding_space_id == before.active_embedding_space_id
    new_chunks = await published(world, after)
    assert len(new_chunks) > len(old_chunks)  # smaller chunks, more of them
    assert not {c.id for c in new_chunks} & {c.id for c in old_chunks}
    for document, version in await world.deps.repository.list_current_versions(
        world.admin, after.id
    ):
        assert version.version == 2, document.title
    assert (await titles(world, "garantia dos equipamentos"))[0] == "garantia.md"


async def test_a_retried_full_reindex_skips_documents_already_enqueued(world: World) -> None:
    await make_kb(world)
    result = await reindex(
        world, mode="full", chunking={"max_tokens": 16, "overlap_tokens": 2}, confirm=True
    )
    assert await world.drain_jobs() == 1 + len(DOCS)
    job = await world.deps.job_queue.get(world.admin, result.job.id)
    assert job.result is not None and job.result["ingestion_jobs"] == len(DOCS)

    # A crashed worker makes the queue requeue the same job. The steps of the job must keep
    # the reindex from creating a second version and ingestion job for every document.
    await world.deps.job_queue.fail(
        world.admin,
        job.id,
        {"message": "Simulated crash."},
        retry=True,
        max_attempts=world.deps.limits.job_max_attempts,
    )
    assert await world.drain_jobs() == 1
    retried = await world.deps.job_queue.get(world.admin, job.id)
    assert retried.status == JobStatus.SUCCEEDED, retried.error
    assert retried.result is not None
    assert retried.result["documents"] == len(DOCS)
    assert retried.result["ingestion_jobs"] == 0
    kb = await kb_now(world)
    for document, version in await world.deps.repository.list_current_versions(world.admin, kb.id):
        assert version.version == 2, document.title
