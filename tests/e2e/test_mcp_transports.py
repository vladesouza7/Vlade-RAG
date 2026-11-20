"""MCP transports: Streamable HTTP with API keys (no port opened) and the stdio command."""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

pytest.importorskip("mcp")

import anyio
import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from tests.e2e.conftest import McpWorld, error_of
from vlade_rag.mcp.server import create_http_app, serve_stdio

pytestmark = pytest.mark.anyio

URL = "http://test/mcp"


@asynccontextmanager
async def http_app(world: McpWorld) -> AsyncIterator[Any]:
    """The HTTP app with its lifespan running (the session manager needs it)."""
    app = create_http_app(world.runtime, host="0.0.0.0")  # noqa: S104 - test: no DNS-rebinding check
    async with app.app.router.lifespan_context(app.app):  # type: ignore[attr-defined]
        yield app


def http(app: Any, key: str | None) -> httpx2.AsyncClient:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test", headers=headers
    )


def mcp_client(app: Any, key: str | None) -> Client:
    return Client(streamable_http_client(URL, http_client=http(app, key)))


async def kb_slugs(client: Client) -> list[str]:
    result = await client.call_tool("vlade_list_knowledge_bases", {})
    return [k["slug"] for k in dict(result.structured_content)["knowledge_bases"]]  # type: ignore[arg-type]


# ---------------------------------------------------------------- HTTP


@pytest.mark.parametrize("key", [None, "", "vrag_nope_nope", "not-an-api-key"])
async def test_http_without_a_valid_key_gets_401(mcp_world: McpWorld, key: str | None) -> None:
    async with http_app(mcp_world) as app, http(app, key) as client:
        ping = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        accept = {"Accept": "application/json, text/event-stream"}
        post = await client.post("/mcp", json=ping, headers=accept)
        assert post.status_code == 401
        assert post.headers["www-authenticate"] == "Bearer"
        assert (await client.get("/mcp", headers=accept)).status_code == 401
        assert (await client.delete("/mcp")).status_code == 401


async def test_http_client_sees_only_its_own_tenant(mcp_world: McpWorld) -> None:
    keys = mcp_world.keys
    async with http_app(mcp_world) as app:
        async with mcp_client(app, keys["admin"]) as acme:
            names = [t.name for t in (await acme.list_tools()).tools]
            assert names[0] == "vlade_list_knowledge_bases"
            assert await kb_slugs(acme) == ["vendas"]
            found = await acme.call_tool(
                "vlade_search", {"knowledge_base": "vendas", "query": "sete dias corridos"}
            )
            assert dict(found.structured_content)["results"]  # type: ignore[arg-type]
        async with mcp_client(app, keys["other"]) as globex:
            assert await kb_slugs(globex) == []
            denied = await globex.call_tool(
                "vlade_search", {"knowledge_base": "vendas", "query": "sete dias corridos"}
            )
            assert error_of(denied)["code"] == "not_found"


async def test_http_each_request_uses_its_own_key(mcp_world: McpWorld) -> None:
    """Stateless server: two keys on the same app never share an identity."""
    keys = mcp_world.keys
    async with (
        http_app(mcp_world) as app,
        mcp_client(app, keys["admin"]) as a,
        mcp_client(app, keys["other"]) as b,
    ):
        assert await kb_slugs(a) == ["vendas"]
        assert await kb_slugs(b) == []
        assert await kb_slugs(a) == ["vendas"]


async def test_http_revoked_key_gets_401(mcp_world: McpWorld) -> None:
    key = mcp_world.keys["reader"]
    async with http_app(mcp_world) as app:
        async with mcp_client(app, key) as client:
            assert await kb_slugs(client) == ["vendas"]
        await mcp_world.runtime.tenants.revoke_api_key(
            mcp_world.reader.tenant_id, key.split("_")[1]
        )
        async with http(app, key) as raw:
            r = await raw.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
            assert r.status_code == 401


async def test_http_audit_records_the_mcp_interface(mcp_world: McpWorld) -> None:
    from vlade_rag.core.application import ListAuditEvents

    async with http_app(mcp_world) as app, mcp_client(app, mcp_world.keys["admin"]) as client:
        await kb_slugs(client)
    events = await ListAuditEvents(mcp_world.runtime.deps).execute(
        mcp_world.admin, action="mcp.tool_call"
    )
    assert [(e.interface, e.resource_type, e.outcome) for e in events] == [
        ("mcp", "vlade_list_knowledge_bases", "success")
    ]
    assert events[0].principal_id == mcp_world.admin.principal_id


# ---------------------------------------------------------------- stdio


async def test_stdio_refuses_a_missing_or_invalid_key(
    mcp_world: McpWorld, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await serve_stdio(mcp_world.runtime, None) == 1
    assert "VLADE_API_KEY" in capsys.readouterr().err
    assert await serve_stdio(mcp_world.runtime, "vrag_nope_nope") == 1
    assert "not a valid API key" in capsys.readouterr().err
    assert capsys.readouterr().out == ""  # stdout carries only the protocol


async def test_stdio_command_end_to_end(mcp_world: McpWorld) -> None:
    """Start ``vlade-rag mcp serve --transport stdio`` as a subprocess, like Claude Code does."""
    url = mcp_world.runtime.settings.database.url
    if url is None:
        pytest.skip("the subprocess needs the PostgreSQL runtime")
    import os

    env = {
        **os.environ,
        "VLADE_DATABASE__URL": url.get_secret_value(),
        "VLADE_SECURITY__API_KEY_PEPPER": "test-pepper",
        "VLADE_OBJECT_STORAGE__BACKEND": "memory",
        "VLADE_API_KEY": mcp_world.keys["admin"],
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from vlade_rag.cli import main; main()",
            "mcp",
            "serve",
            "--transport",
            "stdio",
        ],
        env=env,
    )
    async with Client(params) as client:
        names = [t.name for t in (await client.list_tools()).tools]
        assert "vlade_search" in names
        assert await kb_slugs(client) == ["vendas"]
        result = await client.call_tool(
            "vlade_query", {"knowledge_base": "vendas", "question": "Qual o prazo de troca?"}
        )
        payload = dict(result.structured_content)  # type: ignore[arg-type]
        assert payload["grounded"] is False or payload["citations"] is not None
        json.dumps(payload)


async def test_stdio_command_exits_1_with_a_bad_key(mcp_world: McpWorld) -> None:
    url = mcp_world.runtime.settings.database.url
    if url is None:
        pytest.skip("the subprocess needs the PostgreSQL runtime")
    import os

    env = {
        **os.environ,
        "VLADE_DATABASE__URL": url.get_secret_value(),
        "VLADE_SECURITY__API_KEY_PEPPER": "test-pepper",
        "VLADE_OBJECT_STORAGE__BACKEND": "memory",
        "VLADE_API_KEY": "vrag_nope_nope",
    }
    command = [sys.executable, "-c", "from vlade_rag.cli import main; main()", "mcp", "serve"]
    with anyio.fail_after(60):
        done = await anyio.run_process(command, env=env, check=False)
    assert done.returncode == 1
    assert b"not a valid API key" in done.stderr
    assert done.stdout == b""
