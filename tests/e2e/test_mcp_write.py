"""MCP write tools: tenant flag, roles, confirmation, ingestion, deletion and reindex.

The contract is MCP_SPEC sections 4, 5.7 to 5.9, 9 and 10. Every test runs with the memory
runtime and with PostgreSQL.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("mcp")

import jsonschema

from tests.e2e.conftest import McpWorld, error_of
from tests.e2e.test_mcp import WRITE_TOOLS, listed_read_tools, spec_tools
from vlade_rag.ingestion.worker import Worker
from vlade_rag.mcp.tools import write_tools

pytestmark = pytest.mark.anyio


async def _enable(mcp_world: McpWorld) -> None:
    await mcp_world.runtime.tenants.set_mcp_write_tools(mcp_world.admin.tenant_id, True)


def structured(result: Any) -> dict[str, Any]:
    assert result.structured_content is not None
    return dict(result.structured_content)


async def _audit(mcp_world: McpWorld, name: str) -> list[Any]:
    events = await mcp_world.runtime.deps.audit_log.list_events(
        mcp_world.admin, action="mcp.tool_call", limit=100
    )
    return [e for e in events if e.resource_type == name]


# ---------------------------------------------------------------- gating


async def test_write_tools_are_off_by_default(mcp_world: McpWorld) -> None:
    args = {
        "knowledge_base": "vendas",
        "filename": "novo.md",
        "content_text": "# Novo\n\nTexto novo.",
    }
    async with mcp_world.client(mcp_world.admin) as client:
        assert [t.name for t in (await client.list_tools()).tools] == listed_read_tools(mcp_world)
        error = error_of(await client.call_tool("vlade_ingest_document", args))
    assert error["code"] == "write_tools_disabled" and error["retryable"] is False
    events = await _audit(mcp_world, "vlade_ingest_document")
    assert len(events) == 1 and events[0].outcome == "denied"
    assert events[0].details["error_code"] == "write_tools_disabled"


async def test_enabled_write_tools_are_filtered_by_role(mcp_world: McpWorld) -> None:
    await _enable(mcp_world)
    async with mcp_world.client(mcp_world.admin) as client:
        admin = [t.name for t in (await client.list_tools()).tools]
    async with mcp_world.client(mcp_world.reader) as client:
        reader = [t.name for t in (await client.list_tools()).tools]
        error = error_of(
            await client.call_tool(
                "vlade_delete_document",
                {"knowledge_base": "vendas", "document_id": str(mcp_world.doc_id)},
            )
        )
    assert admin == listed_read_tools(mcp_world) + WRITE_TOOLS
    assert reader == listed_read_tools(mcp_world)
    assert error["code"] == "forbidden"

    spec = {t.name: t for t in write_tools()}
    assert spec["vlade_ingest_document"].read_only is False
    assert spec["vlade_delete_document"].destructive is True
    assert spec["vlade_reindex_knowledge_base"].destructive is True
    contract = spec_tools()
    assert all(t.input_schema == contract[name]["input"] for name, t in spec.items())


# ---------------------------------------------------------------- ingest


async def test_ingest_document_with_text(mcp_world: McpWorld) -> None:
    await _enable(mcp_world)
    secret = "Prazo de trinta dias para troca."
    args = {"knowledge_base": "vendas", "filename": "novo.md", "content_text": secret}
    schema = spec_tools()["vlade_ingest_document"]["output"]
    async with mcp_world.client(mcp_world.admin) as client:
        result = await client.call_tool("vlade_ingest_document", args)
        assert not result.is_error, result
        payload = structured(result)
        jsonschema.validate(payload, schema)
        assert payload["status"] == "pending"
        assert json.loads(result.content[0].text) == payload
        await Worker(mcp_world.runtime, worker_id="mcp-test").run_until_idle()
        job = structured(
            await client.call_tool("vlade_get_ingestion_status", {"job_id": payload["job_id"]})
        )["job"]
        found = structured(
            await client.call_tool("vlade_search", {"knowledge_base": "vendas", "query": secret})
        )
    assert job["status"] == "succeeded"
    assert any(secret in hit["text"] for hit in found["results"])
    assert "trinta dias" not in json.dumps(
        [e.details for e in await _audit(mcp_world, "vlade_ingest_document")]
    )


async def test_ingest_document_rejects_a_bad_source(mcp_world: McpWorld) -> None:
    await _enable(mcp_world)
    args = {
        "knowledge_base": "vendas",
        "filename": "novo.md",
        "content_text": "texto",
        "source_uri": "https://example.com/novo.md",
    }
    async with mcp_world.client(mcp_world.admin) as client:
        both = error_of(await client.call_tool("vlade_ingest_document", args))
        del args["content_text"]
        neither = error_of(await client.call_tool("vlade_ingest_document", args))
        args["source_uri"] = "s3://bucket/a.md"
        s3 = error_of(await client.call_tool("vlade_ingest_document", args))
    assert both["code"] == neither["code"] == "invalid_argument"
    assert s3["code"] == "invalid_argument"  # s3:// needs the S3 backend
    assert "S3 backend" in s3["message"]


# ---------------------------------------------------------------- delete


async def test_delete_document_preview_and_confirm(mcp_world: McpWorld) -> None:
    await _enable(mcp_world)
    args = {"knowledge_base": "vendas", "document_id": str(mcp_world.doc_id)}
    schema = spec_tools()["vlade_delete_document"]["output"]
    async with mcp_world.client(mcp_world.admin) as client:
        preview = structured(await client.call_tool("vlade_delete_document", args))
        jsonschema.validate(preview, schema)
        assert preview["executed"] is False and preview["action"] == "delete_document"
        assert preview["document_title"] == "trocas.md"
        assert preview["will_delete"]["versions"] >= 1
        assert preview["will_delete"]["chunks"] >= 1

        done = structured(
            await client.call_tool("vlade_delete_document", {**args, "confirm": True})
        )
        jsonschema.validate(done, schema)
        assert done["executed"] is True and done["audit_event_id"]
        error = error_of(await client.call_tool("vlade_get_document", args))
    assert error["code"] == "not_found"
    events = await _audit(mcp_world, "vlade_delete_document")
    assert [e.outcome for e in events] == ["success", "preview"]  # newest first


# ---------------------------------------------------------------- reindex


async def test_reindex_preview_confirm_and_conflict(mcp_world: McpWorld) -> None:
    await _enable(mcp_world)
    args = {"knowledge_base": "vendas", "mode": "embeddings"}
    schema = spec_tools()["vlade_reindex_knowledge_base"]["output"]
    async with mcp_world.client(mcp_world.admin) as client:
        preview = structured(await client.call_tool("vlade_reindex_knowledge_base", args))
        jsonschema.validate(preview, schema)
        assert preview["executed"] is False
        assert preview["documents"] == 1 and preview["chunks"] >= 1
        assert preview["estimated_embedding_calls"] >= 1

        done = structured(
            await client.call_tool("vlade_reindex_knowledge_base", {**args, "confirm": True})
        )
        jsonschema.validate(done, schema)
        assert done["executed"] is True and done["job_id"]
        conflict = error_of(
            await client.call_tool("vlade_reindex_knowledge_base", {**args, "confirm": True})
        )
        assert conflict["code"] == "conflict"
        await Worker(mcp_world.runtime, worker_id="mcp-test").run_until_idle()
        found = structured(
            await client.call_tool(
                "vlade_search", {"knowledge_base": "vendas", "query": "sete dias"}
            )
        )
    assert found["results"]
    events = await _audit(mcp_world, "vlade_reindex_knowledge_base")
    assert [e.outcome for e in events] == ["error", "success", "preview"]  # newest first


# ---------------------------------------------------------------- evaluate


async def test_evaluate_uses_a_registered_dataset(mcp_world: McpWorld) -> None:
    await _enable(mcp_world)
    args = {
        "knowledge_base": "vendas",
        "dataset": "legal-ptbr",
        "metrics": ["mrr"],
        "k": 3,
    }
    schema = spec_tools()["vlade_evaluate"]["output"]
    async with mcp_world.client(mcp_world.admin) as client:
        result = await client.call_tool("vlade_evaluate", args)
        assert not result.is_error, result
        payload = structured(result)
        jsonschema.validate(payload, schema)
        await Worker(mcp_world.runtime, worker_id="mcp-test").run_until_idle()
        job = structured(
            await client.call_tool("vlade_get_ingestion_status", {"job_id": payload["job_id"]})
        )["job"]
        missing = error_of(
            await client.call_tool("vlade_evaluate", {**args, "dataset": "nao-existe"})
        )
    assert job["status"] == "succeeded", job["error"]
    assert job["result"]["dataset"] == "legal-ptbr"
    assert "mrr" in job["result"]["metrics"]
    assert missing["code"] == "not_found"
