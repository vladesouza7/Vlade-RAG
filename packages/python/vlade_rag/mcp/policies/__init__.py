"""Rate limits, error mapping and audit of MCP calls (docs/MCP_SPEC.md sections 4, 8, 9, 10).

The server checks the write-tool flag of the tenant before it runs a write tool (task 4.3).
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Mapping
from enum import StrEnum
from typing import Any
from uuid import UUID

from vlade_rag.core.application import Dependencies, EnforceRequestLimits
from vlade_rag.core.domain import (
    AuditEvent,
    PermissionDenied,
    QuotaExceeded,
    RateLimited,
    TenantContext,
    Unauthenticated,
    VladeError,
)

logger = logging.getLogger(__name__)

INTERFACE = "mcp"


class Group(StrEnum):
    """Rate-limit groups (MCP_SPEC section 8)."""

    LIGHT = "light"
    SEARCH = "search"
    GENERATION = "generation"
    WRITE = "write"
    ADMIN = "admin"


# Requests per minute and per API key.
GROUP_LIMITS: dict[Group, int] = {
    Group.LIGHT: 120,
    Group.SEARCH: 60,
    Group.GENERATION: 20,
    Group.WRITE: 30,
    Group.ADMIN: 10,
}


async def enforce_limits(deps: Dependencies, ctx: TenantContext, group: Group) -> None:
    """Apply the limits of the API (key, tenant, daily quota) and the limit of the group."""
    await EnforceRequestLimits(deps).execute(ctx)
    limiter = deps.rate_limiter
    if limiter is None:
        return
    limit = GROUP_LIMITS[group]
    decision = await limiter.take(
        ctx.tenant_id,
        f"mcp:{group.value}:{ctx.principal_id}",
        capacity=limit,
        refill_per_second=limit / 60,
    )
    if not decision.allowed:
        wait = max(math.ceil(decision.retry_after_seconds), 1)
        raise RateLimited(
            f"The API key passed {limit} requests per minute for this group of tools. "
            f"Retry in {wait} s.",
            details={"retry_after_seconds": wait},
        )


# ---------------------------------------------------------------- errors

_RETRYABLE = {"rate_limited", "unavailable", "internal"}
_KNOWN = {
    "invalid_argument",
    "not_found",
    "forbidden",
    "write_tools_disabled",
    "conflict",
    "quota_exceeded",
    "rate_limited",
    "unavailable",
    "internal",
}


def error_payload(exc: Exception, trace_id: str | None) -> dict[str, Any]:
    """The structured error of MCP_SPEC section 9. It never carries internal details."""
    if isinstance(exc, Unauthenticated):
        code, message = "forbidden", "The API key is not valid."
    elif isinstance(exc, VladeError) and exc.code in _KNOWN:
        code, message = exc.code, exc.message
    else:
        code, message = "internal", "Unexpected error."
    return {
        "error": {
            "code": code,
            "message": message,
            "retryable": code in _RETRYABLE,
            "trace_id": trace_id,
        }
    }


def outcome_of(exc: Exception) -> str:
    """Audit outcome of a failed call."""
    if isinstance(exc, PermissionDenied | RateLimited | QuotaExceeded | Unauthenticated):
        return "denied"
    return "error"


# ---------------------------------------------------------------- audit

_HASHED = ("query", "question")
_DROPPED = ("content_text",)


def audit_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Arguments for the audit event: no text content, and a hash instead of a query."""
    out: dict[str, Any] = {}
    for key, value in arguments.items():
        if key in _DROPPED:
            continue
        if key in _HASHED and isinstance(value, str):
            out[f"{key}_sha256"] = hashlib.sha256(value.encode("utf-8")).hexdigest()
        else:
            out[key] = value
    return out


async def record_audit(
    deps: Dependencies,
    ctx: TenantContext,
    *,
    action: str,
    name: str,
    outcome: str,
    arguments: Mapping[str, Any],
    client: Mapping[str, str | None],
    error_code: str | None = None,
    resource_id: str | None = None,
) -> UUID | None:
    """Record one MCP call and return the id of the event. A failure to record is logged and
    does not fail the call."""
    details: dict[str, Any] = {"arguments": audit_arguments(arguments), "client": dict(client)}
    if error_code is not None:
        details["error_code"] = error_code
    try:
        return await deps.audit_log.record(
            ctx,
            AuditEvent(
                tenant_id=ctx.tenant_id,
                principal_id=ctx.principal_id,
                interface=INTERFACE,
                action=action,
                outcome=outcome,
                resource_type=name,
                resource_id=resource_id,
                details=details,
                trace_id=ctx.trace_id or deps.tracer.current_trace_id(),
            ),
        )
    except Exception:
        logger.exception("Could not record the audit event of %s", name)
        return None


__all__ = [
    "GROUP_LIMITS",
    "INTERFACE",
    "Group",
    "audit_arguments",
    "enforce_limits",
    "error_payload",
    "outcome_of",
    "record_audit",
]
