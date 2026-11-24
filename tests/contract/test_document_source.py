"""Contract of the ``DocumentSource`` port: web, Google Drive and SQL run the same tests.

The adapters talk to local fakes, so the suite needs no network and no service. Every adapter
lists items and fetches the bytes of one item through the same methods.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from tests.conftest import _common
from vlade_rag.core.application.deps import SourcePolicy
from vlade_rag.core.domain import RawDocument, Role, SourceItem, TenantContext, uuid7
from vlade_rag.core.ports import DocumentSource
from vlade_rag.ingestion.sources import download
from vlade_rag.ingestion.sources.google_drive import GoogleDriveSource
from vlade_rag.ingestion.sources.sql import SqlSource
from vlade_rag.ingestion.sources.web import WebSource
from vlade_rag.knowledge.memory import memory_adapters

pytestmark = pytest.mark.anyio

HTML = (
    b"<html><head><title>Prazo</title></head><body>"
    b'<a href="/segundo.html">Segundo</a><p>O prazo e de dez dias.</p></body></html>'
)


def make_ctx() -> TenantContext:
    return TenantContext(uuid7(), uuid7(), frozenset({Role.ADMIN}), "library")


class _WebResponse:
    def __init__(self, body: bytes, mime: str) -> None:
        self.is_redirect = False
        self.status_code = 200
        self.headers = {"content-type": mime}
        self._body = body

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        yield self._body


class _WebStream:
    def __init__(self, response: _WebResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _WebResponse:
        return self._response

    async def __aexit__(self, *args: object) -> None:
        return None


class _WebClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> _WebClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def stream(self, method: str, uri: str, **kwargs: object) -> _WebStream:
        body = HTML if uri.endswith("index.html") else b"<html><title>Segundo</title></html>"
        return _WebStream(_WebResponse(body, "text/html; charset=utf-8"))


def _drive_transport(request: httpx2.Request) -> httpx2.Response:
    if request.url.path.endswith("/files") and request.method == "GET":
        return httpx2.Response(
            200,
            json={
                "files": [
                    {
                        "id": "file-1",
                        "name": "prazo.md",
                        "mimeType": "text/markdown",
                        "modifiedTime": "2026-11-23T00:00:00Z",
                    }
                ]
            },
        )
    if "/files/" in request.url.path:
        return httpx2.Response(
            200, content=b"# Prazo\n\nDez dias.", headers={"content-type": "text/markdown"}
        )
    return httpx2.Response(404)


def _drive_client(headers: dict[str, str]) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=httpx2.MockTransport(_drive_transport), headers=headers)


def _sql_database(path: Path) -> str:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE documents (title text, body text)")
    conn.execute("INSERT INTO documents VALUES ('prazo', 'O prazo e de dez dias.')")
    conn.commit()
    conn.close()
    return f"sqlite+aiosqlite:///{path}"


@pytest.fixture(params=["web", "google_drive", "sql"])
async def source(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[DocumentSource, dict[str, Any]]]:
    name = request.param
    if name == "web":
        mem = memory_adapters()
        deps = _common(
            repository=mem.repository,
            vector_index=mem.vector_index,
            lexical_indexes={},
            object_storage=mem.object_storage,
            job_queue=mem.job_queue,
            audit_log=mem.audit_log,
            sources=SourcePolicy(allowed_domains=("example.com",)),
        )
        monkeypatch.setattr(download.httpx2, "AsyncClient", _WebClient)
        yield (
            WebSource(deps, ["https://example.com/index.html"], max_pages=2),
            {
                "source_type": "web",
                "filename": "index.html",
            },
        )
    elif name == "google_drive":
        yield (
            GoogleDriveSource(SecretStr("token"), client_factory=_drive_client),
            {
                "source_type": "gdrive",
                "filename": "prazo.md",
            },
        )
    else:
        adapter = SqlSource(
            SecretStr(_sql_database(tmp_path / "source.db")),
            "SELECT title, body FROM documents",
            filename_columns=("title",),
        )
        try:
            yield adapter, {"source_type": "sql", "filename": "prazo.json"}
        finally:
            await adapter.close()


async def test_list_items(source: tuple[DocumentSource, dict[str, Any]]) -> None:
    adapter, expected = source
    assert isinstance(adapter, DocumentSource)
    items = [item async for item in adapter.list_items(make_ctx(), None)]
    assert items
    assert all(isinstance(item, SourceItem) for item in items)
    assert all(item.uri and item.filename and item.external_id for item in items)
    assert any(item.filename == expected["filename"] for item in items)


async def test_fetch_returns_a_raw_document(source: tuple[DocumentSource, dict[str, Any]]) -> None:
    adapter, expected = source
    items = [item async for item in adapter.list_items(make_ctx(), None)]
    raw = await adapter.fetch(make_ctx(), items[0])
    assert isinstance(raw, RawDocument)
    assert raw.data
    assert raw.source_type == expected["source_type"]
    assert raw.source_uri == items[0].uri
    assert raw.metadata == items[0].metadata


async def test_fetched_document_can_be_ingested(
    source: tuple[DocumentSource, dict[str, Any]],
) -> None:
    adapter, _ = source
    items = [item async for item in adapter.list_items(make_ctx(), None)]
    raw = await adapter.fetch(make_ctx(), items[0])
    assert raw.filename
    assert raw.mime_type
