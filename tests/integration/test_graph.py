"""Knowledge graph use cases (phase 6, ADR-0032) with the in-memory graph index.

The repository runs on memory and on PostgreSQL (fixture ``world``). The graph index is the
deterministic ``MemoryGraphIndex``: it checks the wiring, not the graph quality.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from tests.conftest import World
from vlade_rag.core.application import (
    CreateKnowledgeBase,
    DeleteDocument,
    GetIngestionStatus,
    ReindexGraph,
    Search,
    SearchGraph,
    SubmitIngestion,
)
from vlade_rag.core.domain import (
    InvalidArgument,
    JobKind,
    JobStatus,
    KnowledgeBaseConfig,
    NotFound,
    ProviderUnavailable,
    RawDocument,
    VersionStatus,
)
from vlade_rag.knowledge.memory import MemoryGraphIndex

pytestmark = pytest.mark.anyio

GRUDEM = """# Teologia da Aliança

Wayne Grudem defende a Teologia da Aliança na Teologia Sistemática.
"""
RYRIE = """# Dispensacionalismo

Charles Ryrie defende o Dispensacionalismo e distingue Israel e Igreja.
"""


def graph_config(**retrieval: Any) -> dict[str, Any]:
    return {
        "chunking": {"strategy": "markdown", "max_tokens": 60, "overlap_tokens": 5},
        "embeddings": {"provider": "hashing", "model": "hashing-v1", "dimension": 64},
        "graph": {"enabled": True, "provider": "extractive", "model": "extractive"},
        "retrieval": {"retrievers": ["dense", "lexical", "graph"], **retrieval},
    }


async def _setup(world: World, *, slug: str = "teologia", graph: bool = True) -> None:
    world.deps.graph_index = MemoryGraphIndex()
    config = (
        graph_config()
        if graph
        else {"embeddings": {"provider": "hashing", "model": "hashing-v1", "dimension": 64}}
    )
    await CreateKnowledgeBase(world.deps).execute(world.admin, slug=slug, name="KB", config=config)


async def _ingest(world: World, filename: str, text: str, slug: str = "teologia") -> Any:
    return await SubmitIngestion(world.deps).execute(
        world.admin,
        knowledge_base=slug,
        raw=RawDocument(filename, "text/markdown", text.encode()),
        external_id=filename,
    )


# ---------------------------------------------------------------- configuration


def test_graph_config_validation() -> None:
    with pytest.raises(ValidationError, match=r"graph\.model is required"):
        KnowledgeBaseConfig.model_validate({"graph": {"enabled": True}})
    with pytest.raises(ValidationError, match=r"needs graph\.enabled"):
        KnowledgeBaseConfig.model_validate({"retrieval": {"retrievers": ["dense", "graph"]}})
    config = KnowledgeBaseConfig.model_validate(graph_config())
    assert config.graph.enabled and config.graph.mode == "hybrid"
    assert KnowledgeBaseConfig().graph.enabled is False


# ---------------------------------------------------------------- indexing and search


async def test_ingestion_enqueues_and_runs_the_graph_job(world: World) -> None:
    await _setup(world)
    submitted = await _ingest(world, "grudem.md", GRUDEM)
    assert await world.drain_jobs() == 2  # ingest, then graph_index
    ingest = await GetIngestionStatus(world.deps).execute(world.reader, submitted.job.id)
    assert ingest.result is not None
    graph_job = await GetIngestionStatus(world.deps).execute(
        world.reader, UUID(ingest.result["graph_job_id"])
    )
    assert graph_job.kind == JobKind.GRAPH_INDEX
    assert graph_job.status == JobStatus.SUCCEEDED, graph_job.error
    assert graph_job.result and graph_job.result["chunks"] >= 1
    assert [s.name for s in graph_job.steps] == ["graph_index"]


async def test_graph_search_and_fused_retrieval(world: World) -> None:
    await _setup(world)
    await _ingest(world, "grudem.md", GRUDEM)
    await _ingest(world, "ryrie.md", RYRIE)
    await world.drain_jobs()
    view = await SearchGraph(world.deps).execute(
        world.reader, knowledge_base="teologia", text="Grudem e Ryrie"
    )
    names = {e.name for e in view.entities}
    assert {"Wayne Grudem", "Charles Ryrie"} <= names
    assert view.relations
    assert {c.chunk.document_title for c in view.chunks} == {"grudem.md", "ryrie.md"}
    result = await Search(world.deps).execute(
        world.reader, knowledge_base="teologia", text="Ryrie dispensacionalismo", top_k=3
    )
    assert "Ryrie" in result.results[0].chunk.text


async def test_new_version_replaces_the_graph(world: World) -> None:
    await _setup(world)
    await _ingest(world, "grudem.md", GRUDEM)
    await world.drain_jobs()
    await _ingest(world, "grudem.md", GRUDEM.replace("Wayne Grudem", "Millard Erickson"))
    await world.drain_jobs()
    view = await SearchGraph(world.deps).execute(
        world.reader, knowledge_base="teologia", text="Grudem Erickson"
    )
    names = {e.name for e in view.entities}
    assert "Millard Erickson" in names and "Wayne Grudem" not in names


async def test_delete_document_removes_it_from_the_graph(world: World) -> None:
    await _setup(world)
    submitted = await _ingest(world, "grudem.md", GRUDEM)
    await world.drain_jobs()
    await DeleteDocument(world.deps).execute(
        world.admin, knowledge_base="teologia", document_id=submitted.document.id, confirm=True
    )
    view = await SearchGraph(world.deps).execute(
        world.reader, knowledge_base="teologia", text="Grudem"
    )
    assert view.entities == () and view.chunks == []


async def test_graph_hits_skip_unpublished_chunks(world: World) -> None:
    """Between the publish of a new version and its graph job, old chunks are not returned."""
    await _setup(world)
    await _ingest(world, "grudem.md", GRUDEM)
    await world.drain_jobs()
    await _ingest(world, "grudem.md", GRUDEM + "\nWayne Grudem também escreveu sobre a Igreja.\n")
    claimed = await world.job_queue.claim("w", 60)  # run only the ingest job, not the graph job
    assert claimed is not None and claimed.job.kind == JobKind.INGEST
    from vlade_rag.core.application import RunIngestionJob

    await RunIngestionJob(world.deps).execute(claimed)
    view = await SearchGraph(world.deps).execute(
        world.reader, knowledge_base="teologia", text="Grudem"
    )
    assert view.entities  # the graph still holds the old version
    assert view.chunks == []  # but its chunks are no longer published
    await world.drain_jobs()  # the queue is shared on PostgreSQL: leave it empty


# ---------------------------------------------------------------- failures and guards


async def test_graph_failure_keeps_the_version_published(world: World) -> None:
    class Down(MemoryGraphIndex):
        async def index_document(self, *args: Any, **kwargs: Any) -> int:
            raise ProviderUnavailable("extraction model offline")

    await _setup(world)
    world.deps.graph_index = Down()
    submitted = await _ingest(world, "grudem.md", GRUDEM)
    assert await world.drain_jobs() == 1 + world.deps.limits.job_max_attempts
    version = await world.deps.repository.get_current_version(world.admin, submitted.document.id)
    assert version is not None and version.status == VersionStatus.PUBLISHED
    world.deps.graph_index = MemoryGraphIndex()  # the graph is back; vectors were never lost
    result = await Search(world.deps).execute(
        world.reader, knowledge_base="teologia", text="Grudem aliança", top_k=1
    )
    assert "Grudem" in result.results[0].chunk.text


async def test_graph_needs_server_and_base_support(world: World) -> None:
    await _setup(world, slug="sem-grafo", graph=False)
    with pytest.raises(InvalidArgument, match="not enabled"):
        await SearchGraph(world.deps).execute(
            world.reader, knowledge_base="sem-grafo", text="Grudem"
        )
    await CreateKnowledgeBase(world.deps).execute(
        world.admin, slug="com-grafo", name="KB", config=graph_config()
    )
    world.deps.graph_index = None
    with pytest.raises(InvalidArgument, match="not configured"):
        await Search(world.deps).execute(world.reader, knowledge_base="com-grafo", text="Grudem")


async def test_reindex_graph_preview_and_confirm(world: World) -> None:
    await _setup(world)
    await _ingest(world, "grudem.md", GRUDEM)
    await _ingest(world, "ryrie.md", RYRIE)
    await world.drain_jobs()
    preview = await ReindexGraph(world.deps).execute(
        world.admin, knowledge_base="teologia", confirm=False
    )
    assert (preview.executed, preview.documents, preview.jobs) == (False, 2, 0)
    done = await ReindexGraph(world.deps).execute(
        world.admin, knowledge_base="teologia", confirm=True
    )
    assert (done.executed, done.jobs) == (True, 2)
    assert await world.drain_jobs() == 2


async def test_graph_is_isolated_between_tenants(world: World) -> None:
    await _setup(world)
    await _ingest(world, "grudem.md", GRUDEM)
    await world.drain_jobs()
    with pytest.raises(NotFound):
        await SearchGraph(world.deps).execute(
            world.other_admin, knowledge_base="teologia", text="Grudem"
        )
    await CreateKnowledgeBase(world.deps).execute(
        world.other_admin, slug="teologia", name="Globex", config=graph_config()
    )
    view = await SearchGraph(world.deps).execute(
        world.other_admin, knowledge_base="teologia", text="Grudem"
    )
    assert view.entities == () and view.chunks == []
