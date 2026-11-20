"""Use cases for the quotas and the audit log of a tenant."""

from __future__ import annotations

from dataclasses import dataclass

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import (
    AuditEvent,
    InvalidArgument,
    Role,
    TenantContext,
    TenantQuotas,
    TenantUsage,
)

MAX_AUDIT_EVENTS = 1000


@dataclass(frozen=True, slots=True)
class UsageView:
    quotas: TenantQuotas
    usage: TenantUsage


class GetUsage:
    """Quotas and current usage of the tenant of ``ctx``."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, ctx: TenantContext) -> UsageView:
        ctx.require(Role.READER)
        quotas = (
            await self.deps.tenants.get_quotas(ctx.tenant_id)
            if self.deps.tenants is not None
            else TenantQuotas()
        )
        return UsageView(quotas=quotas, usage=await self.deps.repository.get_usage(ctx))


class ListAuditEvents:
    """Audit events of the tenant of ``ctx``, newest first. Only an administrator reads them."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(
        self,
        ctx: TenantContext,
        *,
        action: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        ctx.require(Role.ADMIN)
        if not 1 <= limit <= MAX_AUDIT_EVENTS:
            raise InvalidArgument(f"The limit must be between 1 and {MAX_AUDIT_EVENTS}.")
        return await self.deps.audit_log.list_events(
            ctx, action=action, outcome=outcome, limit=limit
        )
