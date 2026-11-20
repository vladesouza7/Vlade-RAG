"""Request limits of an interface call (docs/ARCHITECTURE.md section 15).

Three limits apply, in this order: a token bucket per API key, a token bucket per tenant, and the
daily request quota of the tenant. An interface (REST API, MCP server) calls
``EnforceRequestLimits`` once for each authenticated call.
"""

from __future__ import annotations

import math

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import RateLimited, RequestQuotaExceeded, TenantContext

DAILY_KEY = "requests"


class EnforceRequestLimits:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, ctx: TenantContext) -> None:
        """Count the call. Raise ``RateLimited`` or ``RequestQuotaExceeded`` over a limit."""
        limiter = self.deps.rate_limiter
        if limiter is None:
            return
        limits = self.deps.limits
        buckets = (
            (f"key:{ctx.principal_id}", limits.rate_per_key_per_minute, "API key"),
            ("tenant", limits.rate_per_tenant_per_minute, "tenant"),
        )
        for key, per_minute, label in buckets:
            if per_minute <= 0:
                continue
            decision = await limiter.take(
                ctx.tenant_id, key, capacity=per_minute, refill_per_second=per_minute / 60
            )
            if not decision.allowed:
                wait = max(math.ceil(decision.retry_after_seconds), 1)
                raise RateLimited(
                    f"The {label} passed {per_minute} requests per minute. Retry in {wait} s.",
                    details={"retry_after_seconds": wait},
                )
        if self.deps.tenants is None:
            return
        quotas = await self.deps.tenants.get_quotas(ctx.tenant_id)
        if quotas.requests_per_day is None:
            return
        used = await limiter.count_day(ctx.tenant_id, DAILY_KEY, increment=True)
        if used > quotas.requests_per_day:
            raise RequestQuotaExceeded(
                f"The tenant used its {quotas.requests_per_day} requests of the day (UTC).",
            )
