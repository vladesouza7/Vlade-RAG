"""Credentials of the MCP transports (docs/MCP_SPEC.md section 3).

The tenant and the roles always come from the API key. No tool takes a ``tenant_id``.

- ``stdio``: the key comes from ``VLADE_API_KEY`` when the server starts.
- HTTP: every request carries ``Authorization: Bearer <key>``. A missing or invalid key gets 401.
"""

from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from vlade_rag.core.domain import TenantContext, Unauthenticated
from vlade_rag.core.ports import TenantDirectory

CTX_KEY = "vlade.ctx"


def bearer_token(scope: Scope) -> str | None:
    """The token of the ``Authorization: Bearer`` header, or ``None``."""
    for name, value in scope.get("headers", []):
        if name.lower() == b"authorization":
            text = value.decode("latin-1")
            if text.lower().startswith("bearer "):
                return text[7:].strip() or None
    return None


def context_of(request: Any) -> TenantContext | None:
    """The context that ``ApiKeyMiddleware`` stored for this request, if any."""
    scope = getattr(request, "scope", None)
    if scope is None:
        return None
    ctx = scope.get(CTX_KEY)
    return ctx if isinstance(ctx, TenantContext) else None


class ApiKeyMiddleware:
    """ASGI middleware: authenticate the key of each HTTP request before the MCP server runs."""

    def __init__(self, app: ASGIApp, tenants: TenantDirectory) -> None:
        self.app = app
        self.tenants = tenants

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = bearer_token(scope)
        ctx: TenantContext | None = None
        if token is not None:
            try:
                ctx = await self.tenants.authenticate(token, interface="mcp")
            except Unauthenticated:
                ctx = None
        if ctx is None:
            response = JSONResponse(
                {"error": {"code": "unauthenticated", "message": "Send a valid API key."}},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        scope[CTX_KEY] = ctx
        await self.app(scope, receive, send)
