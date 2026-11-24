"""SyncSource feeds a knowledge base from a DocumentSource (task 5.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from tests.conftest import World
from vlade_rag.core.application import CreateKnowledgeBase, SyncSource
from vlade_rag.core.domain import KnowledgeBaseConfig, RawDocument, SourceItem, TenantContext
from vlade_rag.core.domain.kb_config import EmbeddingsConfig


class FakeSource:
    name = "fake"

    def __init__(self) -> None:
        self.items = (
            SourceItem("fake://1", "um.md", "text/markdown", "ext-1", {"n": 1}),
            SourceItem("fake://2", "dois.md", "text/markdown", "ext-2", {"n": 2}),
        )

    async def list_items(self, ctx: TenantContext, cursor: str | None) -> AsyncIterator[SourceItem]:
        for item in self.items:
            yield item

    async def fetch(self, ctx: TenantContext, item: SourceItem) -> RawDocument:
        return RawDocument(
            filename=item.filename,
            mime_type=item.mime_type or "text/markdown",
            data=f"# {item.filename}\n\nConteúdo {item.external_id}.".encode(),
            source_type="fake",
            source_uri=item.uri,
            metadata=dict(item.metadata),
        )


@pytest.mark.anyio
async def test_sync_ingests_items_and_deduplicates(world: World) -> None:
    config = KnowledgeBaseConfig(embeddings=EmbeddingsConfig(provider="h", model="h", dimension=64))
    await CreateKnowledgeBase(world.deps).execute(world.admin, slug="kb", name="KB", config=config)

    source = FakeSource()
    world.deps.document_sources = {"fake": source}  # type: ignore[assignment]
    sync = SyncSource(world.deps)

    first = await sync.execute(world.admin, source="fake", knowledge_base="kb")
    assert first.ingested == 2
    await world.drain_jobs()

    second = await sync.execute(world.admin, source="fake", knowledge_base="kb")
    assert second.ingested == 0
    kb = await world.deps.repository.get_knowledge_base(world.admin, "kb")
    chunks = await world.deps.repository.list_published_chunks(
        world.admin, kb.id, after=None, limit=20
    )
    assert len(chunks) == 2


@pytest.mark.anyio
async def test_configured_connectors_are_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    from vlade_rag.bootstrap import build_runtime
    from vlade_rag.core.config import Settings

    monkeypatch.setenv("VLADE_SOURCES__ALLOWED_DOMAINS", '["example.com"]')
    monkeypatch.setenv("VLADE_SOURCES__WEB__SEEDS", '["https://example.com"]')
    monkeypatch.setenv("VLADE_SOURCES__GOOGLE_DRIVE__ACCESS_TOKEN", "token")
    monkeypatch.setenv("VLADE_SOURCES__SQL__URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("VLADE_SOURCES__SQL__QUERY", "SELECT 1")
    settings = Settings(storage={"backend": "memory"}, object_storage={"backend": "memory"})  # type: ignore[arg-type]
    runtime = await build_runtime(settings, load_plugins=False)
    try:
        assert set(runtime.deps.document_sources) == {"web", "google_drive", "sql"}
    finally:
        await runtime.aclose()


@pytest.mark.anyio
async def test_unknown_source_is_rejected(world: World) -> None:
    sync = SyncSource(world.deps)
    with pytest.raises(Exception, match="not configured"):
        await sync.execute(world.admin, source="missing", knowledge_base="kb")
