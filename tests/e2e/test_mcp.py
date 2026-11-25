"""MCP server: contract, tools, resources, prompts, errors, limits and audit (docs/MCP_SPEC.md)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

import jsonschema
from mcp.shared.exceptions import MCPError
from mcp_types import Implementation

from tests.e2e.conftest import McpWorld, error_of
from vlade_rag.core.application import ListAuditEvents
from vlade_rag.mcp.policies import GROUP_LIMITS, Group
from vlade_rag.mcp.tools import all_tools, read_tools, write_tools

pytestmark = pytest.mark.anyio

SPEC = Path(__file__).parents[2] / "docs" / "MCP_SPEC.md"
READ_TOOLS = [
    "vlade_list_knowledge_bases",
    "vlade_search",
    "vlade_query",
    "vlade_get_document",
    "vlade_get_ingestion_status",
    "vlade_search_graph",
]
WRITE_TOOLS = [
    "vlade_ingest_document",
    "vlade_delete_document",
    "vlade_reindex_knowledge_base",
    "vlade_evaluate",
]


def listed_read_tools(world: McpWorld) -> list[str]:
    """Read tools the server lists: ``vlade_search_graph`` needs a knowledge graph (phase 6)."""
    if world.runtime.deps.graph_index is not None:
        return READ_TOOLS
    return [name for name in READ_TOOLS if name != "vlade_search_graph"]


def spec_tools() -> dict[str, dict[str, Any]]:
    """Description, input schema and output schema of each tool, read from MCP_SPEC.md."""
    parts = re.split(r"^### 5\.\d+\. `(vlade_\w+)`\s*$", SPEC.read_text("utf-8"), flags=re.M)
    tools: dict[str, dict[str, Any]] = {}
    for name, body in zip(parts[1::2], parts[2::2], strict=True):
        quote = [ln[2:] for ln in body.splitlines() if ln.startswith("> ")]
        blocks = re.findall(r"```json\n(.*?)\n```", body, flags=re.S)
        tools[name] = {
            "description": " ".join(quote),
            "input": json.loads(blocks[0]) if blocks else None,
            "output": json.loads(blocks[1]) if len(blocks) > 1 else None,
        }
    return tools


def structured(result: Any) -> dict[str, Any]:
    assert result.structured_content is not None
    return dict(result.structured_content)


# ---------------------------------------------------------------- contract


def test_tool_definitions_match_the_spec() -> None:
    spec = spec_tools()
    tools = {t.name: t for t in all_tools()}
    assert list(tools) == READ_TOOLS + WRITE_TOOLS
    for name, tool in tools.items():
        assert tool.description == spec[name]["description"], name
        assert tool.input_schema == spec[name]["input"], name
        assert tool.output_schema == spec[name]["output"], name
    assert [t.name for t in read_tools()] == READ_TOOLS
    assert [t.name for t in write_tools()] == WRITE_TOOLS


async def test_tools_list_has_annotations_and_schemas(mcp_world: McpWorld) -> None:
    async with mcp_world.client(mcp_world.reader) as client:
        listed = (await client.list_tools()).tools
    assert [t.name for t in listed] == listed_read_tools(mcp_world)
    spec = {t.name: t for t in all_tools()}
    for tool in listed:
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is spec[tool.name].read_only
        assert tool.annotations.destructive_hint is spec[tool.name].destructive
        assert tool.annotations.open_world_hint is False
        assert tool.annotations.idempotent_hint is spec[tool.name].idempotent
        assert tool.input_schema == spec[tool.name].input_schema
        assert tool.output_schema == spec[tool.name].output_schema
    assert next(t for t in listed if t.name == "vlade_query").annotations.idempotent_hint is False  # type: ignore[union-attr]


# ---------------------------------------------------------------- tools


async def test_tools_return_structured_and_text_content(mcp_world: McpWorld) -> None:
    schemas = {t.name: t.output_schema for t in read_tools()}
    calls: list[tuple[str, dict[str, Any]]] = [
        ("vlade_list_knowledge_bases", {}),
        ("vlade_search", {"knowledge_base": "vendas", "query": "prazo de troca", "top_k": 3}),
        ("vlade_query", {"knowledge_base": "vendas", "question": "Qual o prazo de troca?"}),
        (
            "vlade_get_document",
            {"knowledge_base": "vendas", "document_id": str(mcp_world.doc_id)},
        ),
        ("vlade_get_ingestion_status", {"job_id": str(mcp_world.job_id)}),
    ]
    async with mcp_world.client(mcp_world.reader) as client:
        for name, args in calls:
            result = await client.call_tool(name, args)
            assert not result.is_error, (name, result)
            payload = structured(result)
            jsonschema.validate(payload, schemas[name])  # the result obeys its outputSchema
            assert json.loads(result.content[0].text) == payload  # the same JSON as text


async def test_list_search_query(mcp_world: McpWorld) -> None:
    async with mcp_world.client(mcp_world.reader) as client:
        kbs = structured(await client.call_tool("vlade_list_knowledge_bases", {}))
        assert [k["slug"] for k in kbs["knowledge_bases"]] == ["vendas"]
        assert kbs["knowledge_bases"][0]["document_count"] == 1
        assert kbs["knowledge_bases"][0]["updated_at"]

        found = structured(
            await client.call_tool(
                "vlade_search", {"knowledge_base": "vendas", "query": "sete dias corridos"}
            )
        )
        assert found["results"]
        top = found["results"][0]
        assert "sete dias" in top["text"]
        assert top["document_id"] == str(mcp_world.doc_id)
        assert top["resource_uri"] == f"vlade://kb/vendas/documents/{mcp_world.doc_id}"
        assert [r["rank"] for r in found["results"]] == list(range(1, len(found["results"]) + 1))

        answer = structured(
            await client.call_tool(
                "vlade_query", {"knowledge_base": "vendas", "question": "Qual o prazo de troca?"}
            )
        )
        assert answer["grounded"] is True and answer["citations"]
        assert answer["citations"][0]["resource_uri"].startswith("vlade://kb/vendas/documents/")
        assert answer["usage"]["input_tokens"] >= 0


async def test_get_document_and_job(mcp_world: McpWorld) -> None:
    async with mcp_world.client(mcp_world.reader) as client:
        meta = structured(
            await client.call_tool(
                "vlade_get_document",
                {"knowledge_base": "vendas", "document_id": str(mcp_world.doc_id)},
            )
        )["document"]
        assert meta["title"] and meta["version"] == 1 and "text" not in meta

        full = structured(
            await client.call_tool(
                "vlade_get_document",
                {
                    "knowledge_base": "vendas",
                    "document_id": str(mcp_world.doc_id),
                    "include_text": True,
                    "max_chars": 1000,
                },
            )
        )["document"]
        assert "sete dias" in full["text"] and full["truncated"] is False

        job = structured(
            await client.call_tool("vlade_get_ingestion_status", {"job_id": str(mcp_world.job_id)})
        )["job"]
        assert job["status"] == "succeeded"
        assert [s["name"] for s in job["steps"]][-1] == "publish"


# ---------------------------------------------------------------- errors


@pytest.mark.parametrize(
    ("tool", "args", "code"),
    [
        ("vlade_search", {"query": "x"}, "invalid_argument"),  # missing knowledge_base
        ("vlade_search", {"knowledge_base": "vendas", "query": ""}, "invalid_argument"),
        (
            "vlade_search",
            {"knowledge_base": "vendas", "query": "x", "top_k": 999},
            "invalid_argument",
        ),
        (
            "vlade_search",
            {"knowledge_base": "vendas", "query": "x", "extra": 1},
            "invalid_argument",
        ),
        (
            "vlade_get_document",
            {"knowledge_base": "vendas", "document_id": "x"},
            "invalid_argument",
        ),
        ("vlade_get_ingestion_status", {"job_id": "not-a-uuid"}, "invalid_argument"),
        ("vlade_search", {"knowledge_base": "nao-existe", "query": "x"}, "not_found"),
        ("vlade_query", {"knowledge_base": "nao-existe", "question": "x"}, "not_found"),
    ],
)
async def test_tool_errors_are_structured(
    mcp_world: McpWorld, tool: str, args: dict[str, Any], code: str
) -> None:
    async with mcp_world.client(mcp_world.reader) as client:
        result = await client.call_tool(tool, args)
    error = error_of(result)  # also checks isError and the absence of structuredContent
    assert error["code"] == code
    assert error["retryable"] is False
    assert error["message"]
    assert "trace_id" in error


async def test_unknown_tool_is_a_protocol_error(mcp_world: McpWorld) -> None:
    async with mcp_world.client(mcp_world.reader) as client:
        with pytest.raises(MCPError):
            await client.call_tool("vlade_nope", {})


async def test_rate_limit_per_group(mcp_world: McpWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(GROUP_LIMITS, Group.GENERATION, 2)
    args = {"knowledge_base": "vendas", "question": "Qual o prazo de troca?"}
    async with mcp_world.client(mcp_world.reader) as client:
        for _ in range(2):
            assert not (await client.call_tool("vlade_query", args)).is_error
        limited = await client.call_tool("vlade_query", args)
        error = error_of(limited)
        assert error["code"] == "rate_limited" and error["retryable"] is True
        assert "Retry in" in error["message"]
        # Another group of the same key still works.
        assert not (await client.call_tool("vlade_list_knowledge_bases", {})).is_error
    # Another key has its own bucket.
    async with mcp_world.client(mcp_world.admin) as client:
        assert not (await client.call_tool("vlade_query", args)).is_error


# ---------------------------------------------------------------- resources


async def test_resources(mcp_world: McpWorld) -> None:
    async with mcp_world.client(mcp_world.reader) as client:
        listed = (await client.list_resources()).resources
        assert [str(r.uri) for r in listed] == ["vlade://kb/vendas"]  # bases only, no documents
        templates = (await client.list_resource_templates()).resource_templates
        assert [t.uri_template for t in templates] == [
            "vlade://kb/{slug}",
            "vlade://kb/{slug}/documents/{document_id}",
        ]

        kb = await client.read_resource("vlade://kb/vendas")
        assert kb.contents[0].mime_type == "application/json"
        kb_json = json.loads(kb.contents[0].text)  # type: ignore[union-attr]
        assert kb_json["slug"] == "vendas" and kb_json["document_count"] == 1

        doc = await client.read_resource(f"vlade://kb/vendas/documents/{mcp_world.doc_id}")
        doc_json = json.loads(doc.contents[0].text)["document"]  # type: ignore[union-attr]
        assert doc_json["id"] == str(mcp_world.doc_id) and "sete dias" in doc_json["text"]


@pytest.mark.parametrize(
    "uri",
    [
        "vlade://kb/nao-existe",
        "vlade://kb/vendas/documents/00000000-0000-4000-8000-000000000000",
        "vlade://kb/Vendas",
        "vlade://kb/vendas/documents/not-a-uuid",
        "vlade://other/vendas",
    ],
)
async def test_missing_resources_fail_the_same_way(mcp_world: McpWorld, uri: str) -> None:
    async with mcp_world.client(mcp_world.reader) as client:
        with pytest.raises(MCPError) as caught:
            await client.read_resource(uri)
    assert caught.value.error.data["code"] == "not_found"
    assert caught.value.error.message == "The resource does not exist."


# ---------------------------------------------------------------- prompts


async def test_prompts(mcp_world: McpWorld) -> None:
    async with mcp_world.client(mcp_world.reader) as client:
        listed = (await client.list_prompts()).prompts
        assert [p.name for p in listed] == [
            "vlade_answer_with_citations",
            "vlade_summarize_document",
        ]
        assert all(a.required for p in listed for a in (p.arguments or []))

        answer = await client.get_prompt(
            "vlade_answer_with_citations",
            {"knowledge_base": "vendas", "question": "Qual o prazo?"},
        )
        text = answer.messages[0].content.text  # type: ignore[union-attr]
        assert "vlade_search" in text and "vendas" in text and "[n]" in text

        summary = await client.get_prompt(
            "vlade_summarize_document",
            {"knowledge_base": "vendas", "document_id": str(mcp_world.doc_id)},
        )
        assert "vlade_get_document" in summary.messages[0].content.text  # type: ignore[union-attr]

        with pytest.raises(MCPError) as missing:
            await client.get_prompt("vlade_answer_with_citations", {"knowledge_base": "vendas"})
        assert missing.value.error.data["code"] == "invalid_argument"
        with pytest.raises(MCPError):
            await client.get_prompt("nope", {})


# ---------------------------------------------------------------- audit


async def audit(world: McpWorld, action: str) -> list[Any]:
    events = await ListAuditEvents(world.runtime.deps).execute(
        world.admin, action=action, limit=100
    )
    return [e for e in events if e.interface == "mcp"]


async def test_every_call_is_audited(mcp_world: McpWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    question = "Qual o prazo de troca? (texto secreto)"
    info = Implementation(name="pytest-client", version="1.2.3")
    async with mcp_world.client(mcp_world.admin, client_info=info, mode="legacy") as client:
        await client.call_tool("vlade_query", {"knowledge_base": "vendas", "question": question})
        await client.call_tool("vlade_search", {"knowledge_base": "nao-existe", "query": "x"})
        await client.read_resource("vlade://kb/vendas")
        await client.get_prompt(
            "vlade_answer_with_citations", {"knowledge_base": "vendas", "question": question}
        )

    calls = await audit(mcp_world, "mcp.tool_call")
    by_tool = {e.resource_type: e for e in calls}
    ok, failed = by_tool["vlade_query"], by_tool["vlade_search"]
    assert ok.outcome == "success" and failed.outcome == "error"
    assert failed.details["error_code"] == "not_found"
    assert ok.principal_id == mcp_world.admin.principal_id
    assert ok.resource_id == "vendas"
    assert ok.details["client"] == {"name": "pytest-client", "version": "1.2.3"}

    # The text of the question is never stored: only its hash.
    stored = json.dumps([e.details for e in await audit(mcp_world, "mcp.tool_call")])
    assert "secreto" not in stored
    assert ok.details["arguments"]["question_sha256"]
    assert "question" not in ok.details["arguments"]

    assert [e.outcome for e in await audit(mcp_world, "mcp.resource_read")] == ["success"]
    prompts = await audit(mcp_world, "mcp.prompt_get")
    assert [e.outcome for e in prompts] == ["success"]
    assert "secreto" not in json.dumps(prompts[0].details)


async def test_denied_calls_are_audited(
    mcp_world: McpWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(GROUP_LIMITS, Group.GENERATION, 1)
    args = {"knowledge_base": "vendas", "question": "Qual o prazo?"}
    async with mcp_world.client(mcp_world.admin) as client:
        await client.call_tool("vlade_query", args)
        assert (await client.call_tool("vlade_query", args)).is_error
    denied = [e for e in await audit(mcp_world, "mcp.tool_call") if e.outcome == "denied"]
    assert [e.details["error_code"] for e in denied] == ["rate_limited"]
