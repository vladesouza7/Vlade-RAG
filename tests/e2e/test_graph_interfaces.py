"""Knowledge graph over the REST API and the MCP server (phase 6, ADR-0032).

The REST API tests are in ``test_api.py`` (they need its ``api`` fixture). The memory runtime has
the deterministic graph index. The PostgreSQL runtime of these fixtures has no graph database:
there the test checks that the server hides the graph tool.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from tests.e2e.conftest import McpWorld, error_of
from tests.e2e.test_api import GRAPH_KB_CONFIG
from tests.e2e.test_mcp import structured
from vlade_rag.core.application import CreateKnowledgeBase, SubmitIngestion
from vlade_rag.core.domain import RawDocument
from vlade_rag.ingestion.worker import Worker

DOC = "# Escatologia\n\nCharles Ryrie defende o Dispensacionalismo e distingue Israel e Igreja.\n"


def _needs_graph(has_graph: bool) -> None:
    if not has_graph:
        pytest.skip("this runtime has no knowledge graph")


@pytest.mark.anyio
async def test_graph_tool_over_mcp(mcp_world: McpWorld) -> None:
    has_graph = mcp_world.runtime.deps.graph_index is not None
    async with mcp_world.client(mcp_world.reader) as client:
        names = [t.name for t in (await client.list_tools()).tools]
    assert ("vlade_search_graph" in names) is has_graph
    _needs_graph(has_graph)
    async with mcp_world.client(mcp_world.reader) as client:
        error = error_of(
            await client.call_tool("vlade_search_graph", {"knowledge_base": "vendas", "query": "x"})
        )
    assert error["code"] == "invalid_argument"

    deps = mcp_world.runtime.deps
    await CreateKnowledgeBase(deps).execute(
        mcp_world.admin, slug="teologia", name="Teologia", config=GRAPH_KB_CONFIG
    )
    await SubmitIngestion(deps).execute(
        mcp_world.admin,
        knowledge_base="teologia",
        raw=RawDocument("ryrie.md", "text/markdown", DOC.encode()),
    )
    await Worker(mcp_world.runtime, worker_id="graph-test").run_until_idle()
    async with mcp_world.client(mcp_world.reader) as client:
        result = structured(
            await client.call_tool(
                "vlade_search_graph", {"knowledge_base": "teologia", "query": "Charles Ryrie"}
            )
        )
    assert "Charles Ryrie" in {e["name"] for e in result["entities"]}
    assert result["chunks"][0]["resource_uri"].startswith("vlade://kb/teologia/documents/")
    async with mcp_world.client(mcp_world.other) as client:
        other = error_of(
            await client.call_tool(
                "vlade_search_graph", {"knowledge_base": "teologia", "query": "Charles Ryrie"}
            )
        )
    assert other["code"] == "not_found"
