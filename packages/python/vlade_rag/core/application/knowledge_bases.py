"""Knowledge base use cases."""

from __future__ import annotations

import re
from dataclasses import dataclass

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import (
    AuditEvent,
    InvalidArgument,
    KnowledgeBase,
    KnowledgeBaseConfig,
    Role,
    TenantContext,
)

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


@dataclass(frozen=True, slots=True)
class KnowledgeBaseSummary:
    knowledge_base: KnowledgeBase
    document_count: int


class CreateKnowledgeBase:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(
        self,
        ctx: TenantContext,
        *,
        slug: str,
        name: str,
        config: KnowledgeBaseConfig | None = None,
    ) -> KnowledgeBase:
        ctx.require(Role.ADMIN)
        if not _SLUG.match(slug):
            raise InvalidArgument(
                "The slug must have 1 to 63 characters: lowercase letters, digits and hyphens."
            )
        if not name.strip():
            raise InvalidArgument("The name must not be empty.")
        kb = await self.deps.repository.create_knowledge_base(
            ctx, slug=slug, name=name.strip(), config=config or KnowledgeBaseConfig()
        )
        space = await self.deps.repository.get_embedding_space(ctx, kb.active_embedding_space_id)
        await self.deps.vector_index.ensure_space(ctx, space)
        await self.deps.audit_log.record(
            ctx,
            AuditEvent(
                tenant_id=ctx.tenant_id,
                principal_id=ctx.principal_id,
                interface=ctx.interface,
                action="knowledge_base.create",
                outcome="success",
                resource_type="knowledge_base",
                resource_id=str(kb.id),
                details={"slug": slug},
            ),
        )
        return kb


class ListKnowledgeBases:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, ctx: TenantContext) -> list[KnowledgeBaseSummary]:
        ctx.require(Role.READER)
        kbs = await self.deps.repository.list_knowledge_bases(ctx)
        return [
            KnowledgeBaseSummary(kb, await self.deps.repository.count_documents(ctx, kb.id))
            for kb in kbs
        ]


class GetKnowledgeBase:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, ctx: TenantContext, slug: str) -> KnowledgeBaseSummary:
        ctx.require(Role.READER)
        kb = await self.deps.repository.get_knowledge_base(ctx, slug)
        return KnowledgeBaseSummary(kb, await self.deps.repository.count_documents(ctx, kb.id))
