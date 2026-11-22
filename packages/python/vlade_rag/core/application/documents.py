"""Document use cases."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.application.ingestion import document_prefix, text_key
from vlade_rag.core.domain import (
    AuditEvent,
    DeletionReport,
    Document,
    DocumentVersion,
    NotFound,
    Role,
    TenantContext,
)


@dataclass(frozen=True, slots=True)
class DocumentView:
    document: Document
    version: DocumentVersion | None
    text: str | None = None
    truncated: bool = False


class GetDocument:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(
        self,
        ctx: TenantContext,
        *,
        knowledge_base: str,
        document_id: UUID,
        include_text: bool = False,
        max_chars: int = 20_000,
    ) -> DocumentView:
        ctx.require(Role.READER)
        repo = self.deps.repository
        kb = await repo.get_knowledge_base(ctx, knowledge_base)
        document = await repo.get_document(ctx, document_id)
        if document.knowledge_base_id != kb.id:
            raise NotFound("Document does not exist.")
        version = await repo.get_current_version(ctx, document_id)
        if not include_text or version is None:
            return DocumentView(document, version)
        raw = await self.deps.object_storage.get(
            ctx, text_key(kb.id, document_id, version.content_hash)
        )
        text = raw.decode("utf-8")
        limit = max(1, max_chars)
        return DocumentView(document, version, text[:limit], len(text) > limit)


class DeleteDocument:
    """Without ``confirm`` the use case returns a preview and changes nothing."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(
        self, ctx: TenantContext, *, knowledge_base: str, document_id: UUID, confirm: bool
    ) -> DeletionReport:
        ctx.require(Role.ADMIN)
        repo = self.deps.repository
        kb = await repo.get_knowledge_base(ctx, knowledge_base)
        document = await repo.get_document(ctx, document_id)
        if document.knowledge_base_id != kb.id:
            raise NotFound("Document does not exist.")
        report, _keys = await repo.delete_document(ctx, document_id, dry_run=not confirm)
        if confirm:
            await self.deps.object_storage.delete_prefix(ctx, document_prefix(kb.id, document_id))
        event_id = await self.deps.audit_log.record(
            ctx,
            AuditEvent(
                tenant_id=ctx.tenant_id,
                principal_id=ctx.principal_id,
                interface=ctx.interface,
                action="document.delete",
                outcome="success" if confirm else "preview",
                resource_type="document",
                resource_id=str(document_id),
                details={"chunks": report.chunks, "versions": report.versions},
                trace_id=ctx.trace_id,
            ),
        )
        return replace(report, audit_event_id=event_id)
