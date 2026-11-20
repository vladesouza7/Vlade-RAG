"""MCP server: handlers, stdio and Streamable HTTP transports (docs/MCP_SPEC.md).

Every call goes through the same steps: find the caller, check the role, validate the input,
apply the rate limits, run the use case, record the audit event, build the result. An error of
a tool is a result with ``isError: true`` and the error of MCP_SPEC section 9 as JSON text. An error
of a resource or of a prompt is a JSON-RPC error with the same structure in ``data``.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

import jsonschema
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp_types import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    CallToolRequestParams,
    CallToolResult,
    GetPromptRequestParams,
    GetPromptResult,
    ListPromptsResult,
    ListResourcesResult,
    ListResourceTemplatesResult,
    ListToolsResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    TextContent,
    TextResourceContents,
)
from starlette.types import ASGIApp

from vlade_rag import __version__
from vlade_rag.bootstrap import Runtime, build_runtime
from vlade_rag.core.config import Settings, get_settings
from vlade_rag.core.domain import InvalidArgument, NotFound, Role, TenantContext, Unauthenticated
from vlade_rag.mcp import prompts as prompt_defs
from vlade_rag.mcp import resources as resource_defs
from vlade_rag.mcp.auth import ApiKeyMiddleware, context_of
from vlade_rag.mcp.policies import (
    Group,
    enforce_limits,
    error_payload,
    outcome_of,
    record_audit,
)
from vlade_rag.mcp.tools import ToolSpec, read_tools

logger = logging.getLogger(__name__)

NAME = "vlade-rag"
INSTRUCTIONS = (
    "Servidor de conhecimento (RAG). Use `vlade_list_knowledge_bases` para ver as bases. "
    "Use `vlade_search` para ler as fontes ou `vlade_query` para receber uma resposta com "
    "citações. Se `grounded` é false, não complete a resposta com conhecimento próprio sem "
    "avisar o usuário."
)
_NOT_FOUND = "The resource does not exist."


def _client_of(rctx: ServerRequestContext[Any]) -> dict[str, str | None]:
    """Name and version of the MCP client, for the audit event."""
    info = getattr(getattr(rctx.session, "client_params", None), "client_info", None)
    return {"name": getattr(info, "name", None), "version": getattr(info, "version", None)}


def _template_of(uri: str) -> str:
    if uri.startswith("vlade://kb/"):
        return (
            resource_defs.DOCUMENT_TEMPLATE if "/documents/" in uri else resource_defs.KB_TEMPLATE
        )
    return "unknown"


def _validation_message(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    error = jsonschema.exceptions.best_match(
        jsonschema.Draft202012Validator(schema).iter_errors(arguments)
    )
    if error is None:
        return None
    where = ".".join(str(p) for p in error.absolute_path)
    return f"{where}: {error.message}" if where else error.message


def build_server(runtime: Runtime, fixed_ctx: TenantContext | None = None) -> Server[Any]:
    """Build the MCP server.

    ``fixed_ctx`` is the caller of the stdio transport. Without it, the caller of each request
    is the context that ``ApiKeyMiddleware`` stored after it checked the key.
    """
    deps = runtime.deps
    tools: dict[str, ToolSpec] = {spec.name: spec for spec in read_tools()}

    def caller(rctx: ServerRequestContext[Any]) -> TenantContext:
        ctx = fixed_ctx or context_of(rctx.request)
        if ctx is None:
            raise Unauthenticated("The API key is not valid.")
        trace_id = deps.tracer.current_trace_id()
        if trace_id is None or ctx.trace_id == trace_id:
            return ctx
        return TenantContext(ctx.tenant_id, ctx.principal_id, ctx.roles, ctx.interface, trace_id)

    def rpc_error(exc: Exception, ctx: TenantContext | None = None) -> MCPError:
        """A JSON-RPC error for a resource or a prompt, with the structured error in ``data``."""
        if not isinstance(exc, InvalidArgument | NotFound | Unauthenticated) and not hasattr(
            exc, "code"
        ):
            logger.exception("Unexpected error in the MCP server", exc_info=exc)
        error = error_payload(exc, ctx.trace_id if ctx else None)["error"]
        code = INVALID_REQUEST if error["code"] == "forbidden" else INVALID_PARAMS
        if error["code"] in {"rate_limited", "quota_exceeded", "unavailable", "internal"}:
            code = -32603
        return MCPError(code=code, message=error["message"], data=error)

    # ------------------------------------------------------------ tools

    async def on_list_tools(
        rctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        try:
            ctx = caller(rctx)
        except Unauthenticated as exc:
            raise rpc_error(exc) from exc
        return ListToolsResult(tools=[s.to_mcp() for s in tools.values() if ctx.has(s.role)])

    async def on_call_tool(
        rctx: ServerRequestContext[Any], params: CallToolRequestParams
    ) -> CallToolResult:
        spec = tools.get(params.name)
        if spec is None:
            raise MCPError(code=INVALID_PARAMS, message=f"Unknown tool: {params.name}")
        arguments: dict[str, Any] = dict(params.arguments or {})
        client = _client_of(rctx)
        ctx: TenantContext | None = None
        try:
            ctx = caller(rctx)
            ctx.require(spec.role)
            message = _validation_message(spec.input_schema, arguments)
            if message is not None:
                raise InvalidArgument(message)
            await enforce_limits(deps, ctx, spec.group)
            payload = await spec.handler(deps, ctx, arguments)
        except Exception as exc:
            result = error_payload(exc, ctx.trace_id if ctx else deps.tracer.current_trace_id())
            if result["error"]["code"] == "internal":
                logger.exception("Tool %s failed unexpectedly", spec.name, exc_info=exc)
            if ctx is not None:
                await record_audit(
                    deps,
                    ctx,
                    action="mcp.tool_call",
                    name=spec.name,
                    outcome=outcome_of(exc),
                    arguments=arguments,
                    client=client,
                    error_code=result["error"]["code"],
                    resource_id=arguments.get("knowledge_base"),
                )
            # No structuredContent: the error is not an output of the tool, and a client checks
            # structuredContent against the outputSchema (the MCP Inspector does).
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
                is_error=True,
            )
        await record_audit(
            deps,
            ctx,
            action="mcp.tool_call",
            name=spec.name,
            outcome="success",
            arguments=arguments,
            client=client,
            resource_id=arguments.get("knowledge_base"),
        )
        return CallToolResult(
            content=[
                TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))
            ],
            structured_content=payload,
            is_error=False,
        )

    # ------------------------------------------------------------ resources

    async def on_list_resources(
        rctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListResourcesResult:
        try:
            ctx = caller(rctx)
            ctx.require(Role.READER)
            await enforce_limits(deps, ctx, Group.LIGHT)
            return ListResourcesResult(resources=await resource_defs.list_resources(deps, ctx))
        except Exception as exc:
            raise rpc_error(exc) from exc

    async def on_list_resource_templates(
        rctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListResourceTemplatesResult:
        try:
            caller(rctx).require(Role.READER)
        except Exception as exc:
            raise rpc_error(exc) from exc
        return ListResourceTemplatesResult(resource_templates=resource_defs.templates())

    async def on_read_resource(
        rctx: ServerRequestContext[Any], params: ReadResourceRequestParams
    ) -> ReadResourceResult:
        uri = str(params.uri)
        client = _client_of(rctx)
        ctx: TenantContext | None = None
        try:
            ctx = caller(rctx)
            ctx.require(Role.READER)
            await enforce_limits(deps, ctx, Group.LIGHT)
            content = await resource_defs.read_resource(deps, ctx, uri)
        except Exception as exc:
            if isinstance(exc, NotFound):
                exc = NotFound(_NOT_FOUND)  # the same message for every missing resource
            if ctx is not None:
                await record_audit(
                    deps,
                    ctx,
                    action="mcp.resource_read",
                    name=_template_of(uri),
                    outcome=outcome_of(exc),
                    arguments={"uri": uri},
                    client=client,
                    error_code=error_payload(exc, None)["error"]["code"],
                )
            raise rpc_error(exc, ctx) from exc
        await record_audit(
            deps,
            ctx,
            action="mcp.resource_read",
            name=_template_of(uri),
            outcome="success",
            arguments={"uri": uri},
            client=client,
        )
        return ReadResourceResult(
            contents=[
                TextResourceContents(
                    uri=uri, text=resource_defs.to_text(content), mime_type=resource_defs.JSON
                )
            ]
        )

    # ------------------------------------------------------------ prompts

    async def on_list_prompts(
        rctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListPromptsResult:
        try:
            caller(rctx).require(Role.READER)
        except Exception as exc:
            raise rpc_error(exc) from exc
        return ListPromptsResult(prompts=prompt_defs.list_prompts())

    async def on_get_prompt(
        rctx: ServerRequestContext[Any], params: GetPromptRequestParams
    ) -> GetPromptResult:
        arguments = dict(params.arguments or {})
        client = _client_of(rctx)
        ctx: TenantContext | None = None
        try:
            ctx = caller(rctx)
            ctx.require(Role.READER)
            await enforce_limits(deps, ctx, Group.LIGHT)
            result = prompt_defs.get_prompt(params.name, arguments)
        except Exception as exc:
            if ctx is not None:
                await record_audit(
                    deps,
                    ctx,
                    action="mcp.prompt_get",
                    name=params.name,
                    outcome=outcome_of(exc),
                    arguments=arguments,
                    client=client,
                    error_code=error_payload(exc, None)["error"]["code"],
                )
            raise rpc_error(exc, ctx) from exc
        await record_audit(
            deps,
            ctx,
            action="mcp.prompt_get",
            name=params.name,
            outcome="success",
            arguments=arguments,
            client=client,
        )
        return result

    return Server(
        NAME,
        version=__version__,
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
        on_list_resources=on_list_resources,
        on_list_resource_templates=on_list_resource_templates,
        on_read_resource=on_read_resource,
        on_list_prompts=on_list_prompts,
        on_get_prompt=on_get_prompt,
    )


# ---------------------------------------------------------------- transports


def create_http_app(runtime: Runtime, *, host: str = "127.0.0.1") -> ASGIApp:
    """The Streamable HTTP app at ``/mcp``. Stateless: each request carries its own key."""
    server = build_server(runtime)
    app = server.streamable_http_app(stateless_http=True, json_response=True, host=host)
    return ApiKeyMiddleware(app, runtime.tenants)


async def serve_stdio(runtime: Runtime, api_key: str | None) -> int:
    """Run the stdio transport. Return 1, with the reason on stderr, if the key is not valid."""
    if not api_key:
        print("Set VLADE_API_KEY with a key from 'vlade-rag key create'.", file=sys.stderr)
        return 1
    try:
        ctx = await runtime.tenants.authenticate(api_key, interface="mcp")
    except Unauthenticated:
        print("VLADE_API_KEY is not a valid API key.", file=sys.stderr)
        return 1
    server = build_server(runtime, fixed_ctx=ctx)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
    return 0


async def serve_http(settings: Settings | None, host: str, port: int) -> None:
    import uvicorn

    from vlade_rag.observability.opentelemetry import setup_telemetry

    settings = settings or get_settings()
    runtime = await build_runtime(settings, tracer=setup_telemetry(settings))
    try:
        config = uvicorn.Config(
            create_http_app(runtime, host=host),
            host=host,
            port=port,
            log_level=settings.log_level.lower(),
        )
        await uvicorn.Server(config).serve()
    finally:
        await runtime.aclose()
