"""Unit tests of the LLM-Wiki use cases (task 6.12)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from vlade_rag.core.application import (
    DeleteWikiPage,
    GetWikiPage,
    LintWiki,
    ListWikiPages,
    WriteWikiPage,
)
from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import NotFound, Role, TenantContext, WikiPage
from vlade_rag.knowledge.wiki.memory import MemoryWikiStore
from vlade_rag.okf.codec import OkfWikiCodec

_CTX = TenantContext(
    tenant_id=uuid4(), principal_id=uuid4(), roles=frozenset({Role.ADMIN}), interface="test"
)


def _deps(store: MemoryWikiStore) -> Dependencies:
    return cast(Dependencies, SimpleNamespace(wiki_store=store, wiki_codec=OkfWikiCodec()))


def test_write_list_read_and_log() -> None:
    async def _run() -> None:
        store = MemoryWikiStore()
        deps = _deps(store)
        page = WikiPage(
            path="teologia/batismo.md",
            type="Topic",
            title="Batismo",
            description="Estudo sobre o batismo.",
            body="# Batismo\n\nConteúdo.",
        )
        written = await WriteWikiPage(deps).execute(_CTX, "biblia", page)
        assert written.path == "teologia/batismo.md"

        pages = await ListWikiPages(deps).execute(_CTX, "biblia")
        assert [view.path for view in pages] == ["teologia/batismo.md"]
        assert pages[0].page.description == "Estudo sobre o batismo."

        view = await GetWikiPage(deps).execute(_CTX, "biblia", "teologia/batismo.md")
        assert "type: Topic" in view.content
        assert "Batismo" in view.content
        assert await store.get(_CTX, "biblia", "index.md") is not None
        log = await store.get(_CTX, "biblia", "log.md")
        assert log is not None and "Creation" in log

        await WriteWikiPage(deps).execute(
            _CTX, "biblia", WikiPage(path="teologia/batismo.md", type="Topic", body="Novo texto.")
        )
        log = await store.get(_CTX, "biblia", "log.md")
        assert log is not None and "Update" in log

    asyncio.run(_run())


def test_lint_finds_broken_links_and_orphans() -> None:
    async def _run() -> None:
        store = MemoryWikiStore()
        deps = _deps(store)
        await WriteWikiPage(deps).execute(
            _CTX,
            "biblia",
            WikiPage(path="a.md", type="Topic", body="Veja [faltando](faltando.md)."),
        )
        report = await LintWiki(deps).execute(_CTX, "biblia")
        assert report.pages == 1
        assert report.links == 1
        assert any("Broken link: faltando.md" in item for item in report.problems)
        assert "a.md" in report.orphans

    asyncio.run(_run())


def test_delete_updates_the_index() -> None:
    async def _run() -> None:
        store = MemoryWikiStore()
        deps = _deps(store)
        await WriteWikiPage(deps).execute(
            _CTX, "biblia", WikiPage(path="a.md", type="Topic", body="Texto.")
        )
        await DeleteWikiPage(deps).execute(_CTX, "biblia", "a.md")
        assert await ListWikiPages(deps).execute(_CTX, "biblia") == ()
        index = await store.get(_CTX, "biblia", "index.md")
        assert index is not None and "a.md" not in index
        try:
            await GetWikiPage(deps).execute(_CTX, "biblia", "a.md")
        except NotFound:
            pass
        else:
            raise AssertionError("A deleted page must not be readable.")

    asyncio.run(_run())


def test_tenant_isolation() -> None:
    async def _run() -> None:
        store = MemoryWikiStore()
        deps = _deps(store)
        await WriteWikiPage(deps).execute(
            _CTX, "biblia", WikiPage(path="privado.md", type="Topic", body="Texto.")
        )
        other = TenantContext(
            tenant_id=uuid4(), principal_id=uuid4(), roles=frozenset({Role.ADMIN}), interface="test"
        )
        assert await ListWikiPages(deps).execute(other, "biblia") == ()
        assert await store.get(other, "biblia", "privado.md") is None

    asyncio.run(_run())
