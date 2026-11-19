"""FastAPI dependencies: runtime and authentication."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from vlade_rag.bootstrap import Runtime
from vlade_rag.core.domain import TenantContext, Unauthenticated


def get_runtime(request: Request) -> Runtime:
    runtime: Runtime = request.app.state.runtime
    return runtime


async def get_ctx(
    runtime: Annotated[Runtime, Depends(get_runtime)],
    authorization: Annotated[str | None, Header()] = None,
) -> TenantContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthenticated("Send the API key in the header 'Authorization: Bearer <key>'.")
    ctx = await runtime.tenants.authenticate(authorization[7:].strip(), interface="api")
    trace_id = runtime.deps.tracer.current_trace_id()
    if trace_id is None:
        return ctx
    return TenantContext(ctx.tenant_id, ctx.principal_id, ctx.roles, ctx.interface, trace_id)


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
CtxDep = Annotated[TenantContext, Depends(get_ctx)]
