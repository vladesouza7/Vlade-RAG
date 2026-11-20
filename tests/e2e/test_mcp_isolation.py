"""Tenant isolation of the MCP server (roadmap 2.10, RNF-07, docs/MCP_SPEC.md section 12, item 3).

Tenant ``acme`` owns the knowledge base ``vendas``, one document and one ingestion job. Tenant
``globex`` calls every tool, resource and prompt with those identifiers. The response must be
``not_found``, and it must not differ from the response for an identifier that exists nowhere.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

pytest.importorskip("mcp")

from mcp.shared.exceptions import MCPError

from tests.e2e.conftest import KB_CONFIG, McpWorld, error_of
from vlade_rag.core.application import CreateKnowledgeBase

pytestmark = pytest.mark.anyio

NOWHERE_DOC = "00000000-0000-4000-8000-000000000000"


def tool_calls(world: McpWorld, kb: str, doc: str, job: str) -> list[tuple[str, dict[str, Any]]]:
    """Every read tool that takes an identifier, aimed at ``kb``, ``doc`` and ``job``."""
    return [
        ("vlade_search", {"knowledge_base": kb, "query": "prazo de troca"}),
        ("vlade_query", {"knowledge_base": kb, "question": "Qual o prazo de troca?"}),
        ("vlade_get_document", {"knowledge_base": kb, "document_id": doc}),
        ("vlade_get_ingestion_status", {"job_id": job}),
    ]


async def test_foreign_identifiers_are_not_found_in_every_tool(mcp_world: McpWorld) -> None:
    """Knowledge base, document and job of acme: globex has no knowledge base 'vendas'."""
    foreign = tool_calls(mcp_world, "vendas", str(mcp_world.doc_id), str(mcp_world.job_id))
    nowhere = tool_calls(mcp_world, "vendas", NOWHERE_DOC, str(uuid4()))
    async with mcp_world.client(mcp_world.other) as client:
        for (name, args), (_, absent) in zip(foreign, nowhere, strict=True):
            got = error_of(await client.call_tool(name, args))
            expected = error_of(await client.call_tool(name, absent))
            assert got["code"] == "not_found", (name, got)
            # The same answer as for an identifier that does not exist: nothing leaks.
            assert got["code"] == expected["code"] and got["message"] == expected["message"], name


async def test_foreign_document_and_job_in_an_own_knowledge_base(mcp_world: McpWorld) -> None:
    """globex has its own 'vendas'. The document and the job of acme are still not found."""
    await CreateKnowledgeBase(mcp_world.runtime.deps).execute(
        mcp_world.other, slug="vendas", name="Vendas da Globex", config=KB_CONFIG
    )
    async with mcp_world.client(mcp_world.other) as client:
        doc = await client.call_tool(
            "vlade_get_document",
            {"knowledge_base": "vendas", "document_id": str(mcp_world.doc_id)},
        )
        absent = await client.call_tool(
            "vlade_get_document", {"knowledge_base": "vendas", "document_id": NOWHERE_DOC}
        )
        assert error_of(doc)["code"] == "not_found"
        assert error_of(doc)["message"] == error_of(absent)["message"]

        job = await client.call_tool(
            "vlade_get_ingestion_status", {"job_id": str(mcp_world.job_id)}
        )
        assert error_of(job)["code"] == "not_found"


async def test_search_and_query_never_return_text_of_another_tenant(mcp_world: McpWorld) -> None:
    await CreateKnowledgeBase(mcp_world.runtime.deps).execute(
        mcp_world.other, slug="vendas", name="Vendas da Globex", config=KB_CONFIG
    )
    async with mcp_world.client(mcp_world.other) as client:
        found = await client.call_tool(
            "vlade_search", {"knowledge_base": "vendas", "query": "sete dias corridos"}
        )
        assert dict(found.structured_content)["results"] == []  # type: ignore[arg-type]
        answer = dict(
            (
                await client.call_tool(
                    "vlade_query", {"knowledge_base": "vendas", "question": "Qual o prazo?"}
                )
            ).structured_content  # type: ignore[arg-type]
        )
        assert answer["grounded"] is False and answer["citations"] == []
        assert "sete dias" not in json.dumps(answer)


async def test_listing_shows_only_the_own_tenant(mcp_world: McpWorld) -> None:
    async with mcp_world.client(mcp_world.other) as client:
        kbs = dict(
            (await client.call_tool("vlade_list_knowledge_bases", {})).structured_content  # type: ignore[arg-type]
        )
        assert kbs["knowledge_bases"] == []
        assert (await client.list_resources()).resources == []
    async with mcp_world.client(mcp_world.admin) as client:
        assert [str(r.uri) for r in (await client.list_resources()).resources] == [
            "vlade://kb/vendas"
        ]


async def test_foreign_resources_fail_like_missing_ones(mcp_world: McpWorld) -> None:
    foreign = [
        "vlade://kb/vendas",
        f"vlade://kb/vendas/documents/{mcp_world.doc_id}",
    ]
    missing = ["vlade://kb/nao-existe", f"vlade://kb/vendas/documents/{NOWHERE_DOC}"]
    async with mcp_world.client(mcp_world.other) as client:
        for uri in [*foreign, *missing]:
            with pytest.raises(MCPError) as caught:
                await client.read_resource(uri)
            assert caught.value.error.data["code"] == "not_found", uri
            assert caught.value.error.message == "The resource does not exist.", uri


async def test_the_tenant_comes_from_the_key_not_from_the_arguments(mcp_world: McpWorld) -> None:
    """No tool accepts a tenant: an extra argument is rejected, never used."""
    async with mcp_world.client(mcp_world.other) as client:
        result = await client.call_tool(
            "vlade_list_knowledge_bases", {"tenant_id": str(mcp_world.admin.tenant_id)}
        )
        assert error_of(result)["code"] == "invalid_argument"
        result = await client.call_tool(
            "vlade_search",
            {
                "knowledge_base": "vendas",
                "query": "prazo",
                "tenant_id": str(mcp_world.admin.tenant_id),
            },
        )
        assert error_of(result)["code"] == "invalid_argument"


async def test_a_reader_key_has_no_write_access_to_the_server(mcp_world: McpWorld) -> None:
    """The write tools are not offered, and calling one by name is a protocol error."""
    async with mcp_world.client(mcp_world.reader) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert not any(n in names for n in ("vlade_ingest_document", "vlade_delete_document"))
        with pytest.raises(MCPError):
            await client.call_tool("vlade_delete_document", {"knowledge_base": "vendas"})
