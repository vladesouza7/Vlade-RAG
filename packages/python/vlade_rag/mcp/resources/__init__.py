"""MCP resources (docs/MCP_SPEC.md section 6).

``resources/list`` returns the knowledge bases of the tenant, never the documents. A URI that
points to another tenant fails exactly like a URI that does not exist.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from mcp_types import Resource, ResourceTemplate

from vlade_rag.core.application import (
    Dependencies,
    GetDocument,
    GetKnowledgeBase,
    ListKnowledgeBases,
)
from vlade_rag.core.domain import NotFound, TenantContext
from vlade_rag.mcp.tools import document_payload

JSON = "application/json"
MAX_DOCUMENT_CHARS = 100_000

_URI = re.compile(
    r"^vlade://kb/(?P<slug>[a-z0-9][a-z0-9-]{0,62})"
    r"(?:/documents/(?P<document>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}))?$"
)

KB_TEMPLATE = "vlade://kb/{slug}"
DOCUMENT_TEMPLATE = "vlade://kb/{slug}/documents/{document_id}"


def templates() -> list[ResourceTemplate]:
    return [
        ResourceTemplate(
            name="knowledge_base",
            uri_template=KB_TEMPLATE,
            description="Metadados da base e contagem de documentos.",
            mime_type=JSON,
        ),
        ResourceTemplate(
            name="document",
            uri_template=DOCUMENT_TEMPLATE,
            description="Metadados do documento e texto extraído, até 100000 caracteres.",
            mime_type=JSON,
        ),
    ]


async def list_resources(deps: Dependencies, ctx: TenantContext) -> list[Resource]:
    summaries = await ListKnowledgeBases(deps).execute(ctx)
    return [
        Resource(
            uri=f"vlade://kb/{s.knowledge_base.slug}",
            name=s.knowledge_base.slug,
            title=s.knowledge_base.name,
            mime_type=JSON,
        )
        for s in summaries
    ]


async def read_resource(deps: Dependencies, ctx: TenantContext, uri: str) -> dict[str, Any]:
    """The JSON content of a resource. Raises ``NotFound`` for any URI that does not resolve."""
    match = _URI.match(uri)
    if match is None:
        raise NotFound("The resource does not exist.")
    slug = match["slug"]
    if match["document"] is None:
        summary = await GetKnowledgeBase(deps).execute(ctx, slug)
        kb = summary.knowledge_base
        return {
            "slug": kb.slug,
            "name": kb.name,
            "language": kb.language,
            "document_count": summary.document_count,
            "updated_at": None if kb.updated_at is None else kb.updated_at.isoformat(),
        }
    view = await GetDocument(deps).execute(
        ctx,
        knowledge_base=slug,
        document_id=UUID(match["document"]),
        include_text=True,
        max_chars=MAX_DOCUMENT_CHARS,
    )
    return {"document": document_payload(view)}


def to_text(content: dict[str, Any]) -> str:
    return json.dumps(content, ensure_ascii=False, default=str)
