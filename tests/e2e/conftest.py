"""Fixtures of the MCP tests: two tenants, a knowledge base with a document, and clients.

``mcp_world`` runs every test twice: with the memory runtime and with PostgreSQL.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest

from vlade_rag.bootstrap import Runtime, build_runtime
from vlade_rag.core.application import CreateKnowledgeBase, SubmitIngestion
from vlade_rag.core.config import Settings
from vlade_rag.core.domain import RawDocument, Role, TenantContext
from vlade_rag.ingestion.worker import Worker

if TYPE_CHECKING:
    from mcp import Client

KB_CONFIG = {
    "chunking": {"strategy": "markdown", "max_tokens": 60, "overlap_tokens": 5},
    "embeddings": {"provider": "hashing", "model": "hashing-v1", "dimension": 64},
    "generation": {"provider": "extractive", "model": "extractive"},
}
DOC = """# Política de Trocas

## Prazo

O cliente pode trocar o produto em até sete dias corridos após o recebimento.

## Condições

O produto deve estar sem uso e na embalagem original.
"""


def error_of(result: Any) -> dict[str, Any]:
    """The ``error`` object of a failed tool call (MCP_SPEC section 9).

    The JSON is in the text block. A failed call has no ``structuredContent``.
    """
    import json

    assert result.is_error, result
    assert result.structured_content is None
    error = json.loads(result.content[0].text)["error"]
    assert isinstance(error, dict)
    return error


@dataclass
class McpWorld:
    runtime: Runtime
    admin: TenantContext  # acme, role admin
    reader: TenantContext  # acme, role reader
    other: TenantContext  # globex, role admin
    keys: dict[str, str]  # raw API keys, for the HTTP transport
    doc_id: UUID  # document of acme in the knowledge base "vendas"
    job_id: UUID  # ingestion job of that document

    def client(self, ctx: TenantContext, **kwargs: Any) -> Client:
        """An in-process MCP client whose server runs as ``ctx`` (like the stdio transport)."""
        from mcp import Client

        from vlade_rag.mcp.server import build_server

        return Client(build_server(self.runtime, fixed_ctx=ctx), **kwargs)


def _settings(backend: str, request: pytest.FixtureRequest) -> Settings:
    if backend == "memory":
        return Settings(
            storage={"backend": "memory"},  # type: ignore[arg-type]
            object_storage={"backend": "memory"},  # type: ignore[arg-type]
        )
    _, app_url = request.getfixturevalue("postgres_urls")
    return Settings(
        database={"url": app_url},  # type: ignore[arg-type]
        security={"api_key_pepper": "test-pepper"},  # type: ignore[arg-type]
        object_storage={"backend": "memory"},  # type: ignore[arg-type]
    )


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.integration)])
async def mcp_world(request: pytest.FixtureRequest) -> AsyncIterator[McpWorld]:
    pytest.importorskip("mcp")
    runtime = await build_runtime(_settings(request.param, request), load_plugins=False)
    try:
        tenants = runtime.tenants
        suffix = secrets.token_hex(3)
        acme = await tenants.create_tenant(f"acme-{suffix}", "ACME")
        globex = await tenants.create_tenant(f"globex-{suffix}", "Globex")
        keys: dict[str, str] = {}
        contexts: dict[str, TenantContext] = {}
        for label, tenant, role in (
            ("admin", acme, Role.ADMIN),
            ("reader", acme, Role.READER),
            ("other", globex, Role.ADMIN),
        ):
            issued = await tenants.issue_api_key(
                tenant.id, principal_name=label, roles=frozenset({role})
            )
            keys[label] = issued.key
            contexts[label] = await tenants.authenticate(issued.key, interface="mcp")

        admin = contexts["admin"]
        await CreateKnowledgeBase(runtime.deps).execute(
            admin, slug="vendas", name="Vendas", config=KB_CONFIG
        )
        submitted = await SubmitIngestion(runtime.deps).execute(
            admin,
            knowledge_base="vendas",
            raw=RawDocument(filename="trocas.md", mime_type="text/markdown", data=DOC.encode()),
            external_id="trocas",
        )
        await Worker(runtime, worker_id="test").run_until_idle()
        yield McpWorld(
            runtime,
            admin,
            contexts["reader"],
            contexts["other"],
            keys,
            submitted.document.id,
            submitted.job.id,
        )
    finally:
        await runtime.aclose()
