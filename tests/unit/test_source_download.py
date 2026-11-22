"""Origin URI policy of the write tool (ARCHITECTURE section 15, MCP_SPEC section 5.7)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, ClassVar
from uuid import uuid4

import pytest

from vlade_rag.core.application.deps import Limits, SourcePolicy
from vlade_rag.core.domain import InvalidArgument, QuotaExceeded, Role, TenantContext
from vlade_rag.ingestion.sources import download as sources


def deps(allowed: tuple[str, ...] = (), max_bytes: int = 1024) -> Any:
    return SimpleNamespace(
        object_storage=SimpleNamespace(),
        sources=SourcePolicy(allowed_domains=allowed, max_bytes=max_bytes),
        limits=Limits(max_upload_bytes=10_000),
    )


def ctx() -> TenantContext:
    return TenantContext(uuid4(), uuid4(), frozenset({Role.ADMIN}), "mcp")


@pytest.mark.parametrize(
    ("host", "allowed", "expected"),
    [
        ("example.com", ["example.com"], True),
        ("docs.example.com", ["example.com"], True),
        ("example.com.br", ["example.com"], False),
        ("EXAMPLE.COM.", ["example.com"], True),
        ("example.com", [], False),
        ("example.com", ["", "other.com"], False),
    ],
)
def test_host_allowed(host: str, allowed: list[str], expected: bool) -> None:
    assert sources.host_allowed(host, allowed) is expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    "uri", ["http://example.com/a.md", "ftp://example.com/a.md", "file:///a.md"]
)
async def test_only_https_and_s3_are_accepted(uri: str) -> None:
    with pytest.raises(InvalidArgument, match="s3:// or https://"):
        await sources.read_source(deps(("example.com",)), ctx(), uri)


@pytest.mark.anyio
async def test_https_needs_an_allowlist() -> None:
    with pytest.raises(InvalidArgument, match="ALLOWED_DOMAINS"):
        await sources.read_source(deps(), ctx(), "https://example.com/a.md")


@pytest.mark.anyio
async def test_https_refuses_a_host_outside_the_allowlist() -> None:
    with pytest.raises(InvalidArgument, match="not in the allowed domains"):
        await sources.read_source(deps(("good.com",)), ctx(), "https://example.com/a.md")


@pytest.mark.anyio
async def test_https_refuses_a_private_address() -> None:
    with pytest.raises(InvalidArgument, match="private or link-local"):
        await sources.read_source(deps(("localhost",)), ctx(), "https://localhost/a.md")


@pytest.mark.anyio
async def test_https_refuses_another_port() -> None:
    with pytest.raises(InvalidArgument, match="port 443"):
        await sources.read_source(deps(("example.com",)), ctx(), "https://example.com:8443/a.md")


class _Response:
    is_redirect = False
    status_code = 200
    headers: ClassVar[dict[str, str]] = {"content-type": "text/markdown; charset=utf-8"}

    async def aiter_bytes(self) -> Any:
        yield b"abc"
        yield b"def"


class _Stream:
    async def __aenter__(self) -> _Response:
        return _Response()

    async def __aexit__(self, *args: Any) -> None:
        return None


class _Client:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def stream(self, method: str, uri: str) -> _Stream:
        return _Stream()


@pytest.mark.anyio
async def test_https_download(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources.httpx2, "AsyncClient", _Client)

    async def public(host: str) -> None:
        return None

    monkeypatch.setattr(sources, "_check_public", public)
    content = await sources.read_source(deps(("example.com",)), ctx(), "https://example.com/a.md")
    assert content.data == b"abcdef" and content.mime_type == "text/markdown"


@pytest.mark.anyio
async def test_https_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources.httpx2, "AsyncClient", _Client)

    async def public(host: str) -> None:
        return None

    monkeypatch.setattr(sources, "_check_public", public)
    with pytest.raises(QuotaExceeded):
        await sources.read_source(
            deps(("example.com",), max_bytes=4), ctx(), "https://example.com/a.md"
        )


class _Storage:
    bucket = "bucket"

    def __init__(self) -> None:
        self.key = ""

    async def get(self, ctx: TenantContext, key: str) -> bytes:
        self.key = key
        return b"conteudo"


@pytest.mark.anyio
async def test_s3_reads_an_object_of_the_tenant() -> None:
    tenant = ctx()
    storage = _Storage()
    dependencies = deps()
    dependencies.object_storage = storage
    uri = f"s3://bucket/{tenant.tenant_id}/imports/a.md"
    content = await sources.read_source(dependencies, tenant, uri)
    assert content.data == b"conteudo" and storage.key == "imports/a.md"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "uri",
    ["s3://bucket/a.md", "s3://other/00000000-0000-4000-8000-000000000000/a.md", "s3://bucket/"],
)
async def test_s3_refuses_a_foreign_object(uri: str) -> None:
    dependencies = deps()
    dependencies.object_storage = _Storage()
    with pytest.raises(InvalidArgument):
        await sources.read_source(dependencies, ctx(), uri)
