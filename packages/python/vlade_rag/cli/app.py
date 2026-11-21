"""Typer application for the ``vlade-rag`` command (docs/ARCHITECTURE.md section 14.3)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID

import typer

from vlade_rag import __version__
from vlade_rag.core.config import get_settings
from vlade_rag.core.domain import Role, TenantContext, VladeError
from vlade_rag.native import backend, engine_version

app = typer.Typer(name="vlade-rag", no_args_is_help=True, add_completion=False)
api_app = typer.Typer(help="REST API commands.", no_args_is_help=True)
db_app = typer.Typer(help="Database commands (owner credentials).", no_args_is_help=True)
tenant_app = typer.Typer(help="Tenant administration.", no_args_is_help=True)
key_app = typer.Typer(help="API key administration.", no_args_is_help=True)
kb_app = typer.Typer(help="Knowledge bases.", no_args_is_help=True)
audit_app = typer.Typer(help="Audit log of the tenant.", no_args_is_help=True)
mcp_app = typer.Typer(help="MCP server.", no_args_is_help=True)
eval_app = typer.Typer(help="Quality evaluation.", no_args_is_help=True)
app.add_typer(audit_app, name="audit")
app.add_typer(eval_app, name="eval")
app.add_typer(mcp_app, name="mcp")
app.add_typer(api_app, name="api")
app.add_typer(db_app, name="db")
app.add_typer(tenant_app, name="tenant")
app.add_typer(key_app, name="key")
app.add_typer(kb_app, name="kb")

SUPPORTED_SUFFIXES = {".txt", ".text", ".md", ".markdown", ".html", ".htm", ".pdf", ".docx"}


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        return asyncio.run(coro)
    except VladeError as exc:
        typer.echo(f"Error ({exc.code}): {exc.message}", err=True)
        raise typer.Exit(2) from exc


async def _with_runtime[T](fn: Callable[[Any], Awaitable[T]]) -> T:
    from vlade_rag.bootstrap import build_runtime

    runtime = await build_runtime(get_settings())
    try:
        return await fn(runtime)
    finally:
        await runtime.aclose()


async def _ctx(runtime: Any) -> TenantContext:
    key = os.environ.get("VLADE_API_KEY")
    if not key:
        typer.echo("Set VLADE_API_KEY with a key from 'vlade-rag key create'.", err=True)
        raise typer.Exit(2)
    ctx: TenantContext = await runtime.tenants.authenticate(key, interface="cli")
    return ctx


def _limit_text(value: int | None) -> str:
    return "unlimited" if value is None else str(value)


def _print_json(data: Any) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))


# ---------------------------------------------------------------- general


@app.command()
def version() -> None:
    """Print the package version and the active native backend."""
    native = engine_version()
    suffix = f" (vlade-rag-core {native})" if native else ""
    typer.echo(f"vlade-rag {__version__} backend={backend()}{suffix}")


@api_app.command("serve")
def api_serve(
    host: str | None = typer.Option(None, help="Bind address. Default: VLADE_API__HOST."),
    port: int | None = typer.Option(None, help="Port. Default: VLADE_API__PORT."),
) -> None:
    """Run the REST API with Uvicorn."""
    try:
        import uvicorn
    except ImportError as exc:
        typer.echo('The API needs the "api" extra: pip install "vlade-rag[api]"', err=True)
        raise typer.Exit(1) from exc
    from vlade_rag.observability.logging import configure_logging

    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.environment != "dev")
    uvicorn.run(
        "vlade_rag.api.app:create_app",
        factory=True,
        host=host or settings.api.host,
        port=port or settings.api.port,
        log_level=settings.log_level.lower(),
    )


@eval_app.command("run")
def eval_run(
    knowledge_base: str,
    dataset: Path = typer.Option(..., help="JSON Lines file: question and relevant_documents."),
    k: int = typer.Option(
        10, min=1, help="The largest cutoff of Recall@K, Precision@K and NDCG@K."
    ),
    output: Path | None = typer.Option(None, help="Write the full report (JSON) to this file."),
    as_json: bool = typer.Option(False, "--json", help="Print the full report as JSON."),
    rerank_model: str | None = typer.Option(
        None,
        help="Rerank with this model for this run only. The knowledge base is not changed.",
    ),
    rerank_provider: str = typer.Option(
        "openrouter", help="The provider of --rerank-model (a plugin of kind 'reranker')."
    ),
    retrievers: str | None = typer.Option(
        None,
        help="Comma-separated retrievers for this run only, for example dense,lexical,fuzzy.",
    ),
    query_transform: str | None = typer.Option(
        None,
        help="Query transform for this run only: none, rewrite, multi_query or hyde.",
    ),
) -> None:
    """Score the retrieval of a knowledge base with a dataset. Needs the admin role.

    The scoring uses no LLM. A reranker or a query transform calls the provider you choose.
    """
    from pydantic import ValidationError

    from vlade_rag.core.domain.kb_config import RerankConfig, RetrievalConfig
    from vlade_rag.evaluation.datasets import load_dataset
    from vlade_rag.evaluation.retrieval import RetrievalEvaluator

    rerank = (
        RerankConfig(enabled=True, provider=rerank_provider, model=rerank_model)
        if rerank_model
        else None
    )
    try:
        # model_validate checks the values at run time: the options arrive as plain text.
        overrides = RetrievalConfig.model_validate(
            {
                "retrievers": tuple(r.strip() for r in retrievers.split(",") if r.strip())
                if retrievers
                else ("dense", "lexical"),
                "query_transform": query_transform or "none",
            }
        )
    except ValidationError as exc:
        typer.echo(f"Invalid option: {exc.errors()[0]['msg']}", err=True)
        raise typer.Exit(2) from exc
    names = overrides.retrievers if retrievers else None
    transform = overrides.query_transform if query_transform else None

    async def go(rt: Any) -> Any:
        items = load_dataset(dataset)
        ctx = await _ctx(rt)
        kb = await rt.deps.repository.get_knowledge_base(ctx, knowledge_base)
        evaluator = RetrievalEvaluator(
            rt.deps,
            rerank=rerank,
            retrievers=names,
            query_transform=transform,
        )
        return await evaluator.evaluate(ctx, kb, items, k)

    report = _run(_with_runtime(go))
    payload = {
        "metrics": dict(report.metrics),
        "config": dict(report.config),
        "items": report.items,
        "details": [dict(d) for d in report.details],
    }
    if output is not None:
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")
    if as_json:
        _print_json(payload)
        return
    typer.echo(f"{report.items} questions, knowledge base '{knowledge_base}'")
    for name, value in sorted(report.metrics.items()):
        typer.echo(f"  {name:<14}{value:.4f}")
    misses = [
        d
        for d in report.details
        if d["first_relevant_rank"] in (None,) or d["first_relevant_rank"] > k
    ]
    typer.echo(f"Questions without a relevant document in the first {k}: {len(misses)}")
    for d in misses:
        typer.echo(f"  - {d['question']}")


@mcp_app.command("serve")
def mcp_serve(
    transport: str = typer.Option("stdio", help="stdio or http."),
    host: str = typer.Option("127.0.0.1", help="Bind address of the http transport."),
    port: int = typer.Option(8765, help="Port of the http transport."),
) -> None:
    """Run the MCP server. stdio reads VLADE_API_KEY; http reads the key of each request."""
    if transport not in ("stdio", "http"):
        typer.echo("The transport must be 'stdio' or 'http'.", err=True)
        raise typer.Exit(2)
    try:
        from vlade_rag.mcp.server import serve_http, serve_stdio
    except ImportError as exc:
        typer.echo('The MCP server needs the "mcp" extra: pip install "vlade-rag[mcp]"', err=True)
        raise typer.Exit(1) from exc
    from vlade_rag.observability.logging import configure_logging

    settings = get_settings()
    if transport == "http":
        configure_logging(settings.log_level, json_output=settings.environment != "dev")
        _run(serve_http(settings, host, port))
        return
    # stdout carries the protocol: logs go to stderr.
    configure_logging(settings.log_level, json_output=True, stream=sys.stderr)

    async def go(rt: Any) -> int:
        return await serve_stdio(rt, os.environ.get("VLADE_API_KEY"))

    raise typer.Exit(_run(_with_runtime(go)))


@app.command()
def worker(
    until_idle: bool = typer.Option(False, help="Process pending jobs, then exit."),
) -> None:
    """Run the ingestion worker."""
    from vlade_rag.ingestion.worker import Worker
    from vlade_rag.observability.logging import configure_logging

    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.environment != "dev")

    async def go(rt: Any) -> None:
        w = Worker(rt)
        if until_idle:
            typer.echo(f"Processed {await w.run_until_idle()} jobs.")
        else:
            await w.run()

    _run(_with_runtime(go))


# ---------------------------------------------------------------- database and administration


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Apply database migrations and configure the application role."""
    from vlade_rag.knowledge.postgres.migrate import upgrade

    db = get_settings().database
    if db.owner_url is None:
        typer.echo("Set VLADE_DATABASE__OWNER_URL (database owner credentials).", err=True)
        raise typer.Exit(2)
    app_url = db.url.get_secret_value() if db.url else None
    applied = _run(upgrade(db.owner_url.get_secret_value(), app_url))
    typer.echo(f"Applied: {', '.join(applied)}" if applied else "Database is up to date.")


@tenant_app.command("create")
def tenant_create(slug: str, name: str = typer.Option(None, help="Display name.")) -> None:
    """Create a tenant."""

    async def go(rt: Any) -> Any:
        return await rt.tenants.create_tenant(slug, name or slug)

    tenant = _run(_with_runtime(go))
    typer.echo(f"Tenant '{tenant.slug}' created: {tenant.id}")


@tenant_app.command("quota")
def tenant_quota(
    slug: str,
    documents: int | None = typer.Option(None, min=0, help="Maximum number of documents."),
    size: int | None = typer.Option(None, "--bytes", min=0, help="Maximum stored bytes."),
    requests_per_day: int | None = typer.Option(
        None, "--requests-per-day", min=0, help="Maximum requests per UTC day."
    ),
    clear: bool = typer.Option(False, help="Remove every limit."),
) -> None:
    """Show the quotas of a tenant. With options, change only the given limits."""
    from vlade_rag.core.domain import TenantQuotas

    async def go(rt: Any) -> tuple[TenantQuotas, bool]:
        tenant = await rt.tenants.get_tenant(slug)
        current = await rt.tenants.get_quotas(tenant.id)
        if not clear and documents is None and size is None and requests_per_day is None:
            return current, False
        new = (
            TenantQuotas()
            if clear
            else TenantQuotas(
                documents=current.documents if documents is None else documents,
                bytes=current.bytes if size is None else size,
                requests_per_day=(
                    current.requests_per_day if requests_per_day is None else requests_per_day
                ),
            )
        )
        await rt.tenants.set_quotas(tenant.id, new)
        return new, True

    quotas, changed = _run(_with_runtime(go))
    typer.echo(
        f"{'Updated: ' if changed else ''}"
        f"documents={_limit_text(quotas.documents)} bytes={_limit_text(quotas.bytes)} "
        f"requests_per_day={_limit_text(quotas.requests_per_day)}"
    )


@key_app.command("list")
def key_list(tenant: str = typer.Option(..., help="Tenant slug.")) -> None:
    """List the API keys of a tenant. The secret is never shown."""

    async def go(rt: Any) -> Any:
        t = await rt.tenants.get_tenant(tenant)
        return await rt.tenants.list_api_keys(t.id)

    for k in _run(_with_runtime(go)):
        status = "revoked" if k.revoked else "active"
        roles = ",".join(sorted(r.value for r in k.roles))
        typer.echo(f"{k.key_prefix}\t{status}\t{roles}\t{k.principal_name}")


@key_app.command("revoke")
def key_revoke(
    key_prefix: str,
    tenant: str = typer.Option(..., help="Tenant slug."),
) -> None:
    """Revoke an API key by its prefix (see 'key list')."""

    async def go(rt: Any) -> None:
        t = await rt.tenants.get_tenant(tenant)
        await rt.tenants.revoke_api_key(t.id, key_prefix)

    _run(_with_runtime(go))
    typer.echo(f"Key '{key_prefix}' revoked.")


@key_app.command("create")
def key_create(
    tenant: str = typer.Option(..., help="Tenant slug."),
    roles: str = typer.Option("reader", help="Comma-separated roles: reader, writer, admin."),
    name: str = typer.Option("cli", help="Principal name."),
) -> None:
    """Issue an API key. The key is shown once."""
    parsed = frozenset(Role(r.strip()) for r in roles.split(",") if r.strip())

    async def go(rt: Any) -> Any:
        t = await rt.tenants.get_tenant(tenant)
        return await rt.tenants.issue_api_key(t.id, principal_name=name, roles=parsed)

    issued = _run(_with_runtime(go))
    typer.echo(issued.key)
    typer.echo(f"Roles: {', '.join(sorted(r.value for r in issued.roles))}", err=True)


# ---------------------------------------------------------------- knowledge bases


def _load_config(path: Path | None) -> dict[str, Any] | None:
    """Read a (possibly partial) configuration. None: use the server default."""
    if path is None:
        return None
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            typer.echo("YAML needs PyYAML. Use a .json file instead.", err=True)
            raise typer.Exit(2) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        typer.echo("The configuration file must contain an object.", err=True)
        raise typer.Exit(2)
    return data


@kb_app.command("create")
def kb_create(
    slug: str,
    name: str = typer.Option(None, help="Display name."),
    config: Path | None = typer.Option(None, help="JSON or YAML file with the configuration."),
) -> None:
    """Create a knowledge base."""
    from vlade_rag.core.application import CreateKnowledgeBase

    cfg = _load_config(config)

    async def go(rt: Any) -> Any:
        return await CreateKnowledgeBase(rt.deps).execute(
            await _ctx(rt), slug=slug, name=name or slug, config=cfg
        )

    kb = _run(_with_runtime(go))
    typer.echo(f"Knowledge base '{kb.slug}' created: {kb.id}")


@kb_app.command("list")
def kb_list() -> None:
    """List the knowledge bases of the tenant."""
    from vlade_rag.core.application import ListKnowledgeBases

    async def go(rt: Any) -> Any:
        return await ListKnowledgeBases(rt.deps).execute(await _ctx(rt))

    for s in _run(_with_runtime(go)):
        typer.echo(
            f"{s.knowledge_base.slug}\t{s.document_count} documents\t{s.knowledge_base.name}"
        )


# ---------------------------------------------------------------- documents and queries


def _collect(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                p for p in sorted(path.rglob("*")) if p.suffix.lower() in SUPPORTED_SUFFIXES
            )
        elif path.is_file():
            files.append(path)
        else:
            typer.echo(f"Not found: {path}", err=True)
    return files


@app.command()
def ingest(
    knowledge_base: str,
    paths: list[Path],
    wait: bool = typer.Option(False, help="Run the pending jobs in this process and wait."),
    metadata: str = typer.Option("{}", help="JSON metadata for every document."),
) -> None:
    """Ingest files or folders. The external id is the relative file path."""
    from vlade_rag.core.application import SubmitIngestion
    from vlade_rag.core.domain import RawDocument
    from vlade_rag.ingestion.worker import Worker

    meta = json.loads(metadata)
    files = _collect(paths)
    if not files:
        typer.echo("No supported files found.", err=True)
        raise typer.Exit(2)

    async def go(rt: Any) -> tuple[int, int, list[UUID]]:
        ctx = await _ctx(rt)
        submitted = skipped = 0
        jobs = []
        for path in files:
            try:
                result = await SubmitIngestion(rt.deps).execute(
                    ctx,
                    knowledge_base=knowledge_base,
                    raw=RawDocument(
                        filename=path.name,
                        mime_type="",
                        data=path.read_bytes(),
                        source_type="file",
                        source_uri=path.as_posix(),
                        metadata=meta,
                    ),
                    external_id=path.as_posix(),
                )
            except VladeError as exc:
                typer.echo(f"Skipped {path}: {exc.message}", err=True)
                continue
            jobs.append(result.job.id)
            skipped += result.skipped
            submitted += not result.skipped
        if wait:
            await Worker(rt, worker_id="cli").run_until_idle()
        return submitted, skipped, jobs

    submitted, skipped, jobs = _run(_with_runtime(go))
    typer.echo(f"Submitted {submitted} documents ({skipped} unchanged). Jobs: {len(jobs)}.")


@app.command()
def usage(as_json: bool = typer.Option(False, "--json")) -> None:
    """Show the quotas and the usage of the tenant."""
    from vlade_rag.core.application import GetUsage

    async def go(rt: Any) -> Any:
        return await GetUsage(rt.deps).execute(await _ctx(rt))

    view = _run(_with_runtime(go))
    q = view.quotas
    data = {
        "documents": view.usage.documents,
        "bytes": view.usage.bytes,
        "requests_today": view.usage.requests_today,
        "quotas": {
            "documents": q.documents,
            "bytes": q.bytes,
            "requests_per_day": q.requests_per_day,
        },
    }
    if as_json:
        _print_json(data)
        return
    typer.echo(f"documents: {view.usage.documents} / {_limit_text(q.documents)}")
    typer.echo(f"bytes: {view.usage.bytes} / {_limit_text(q.bytes)}")
    typer.echo(f"requests today: {view.usage.requests_today} / {_limit_text(q.requests_per_day)}")


@audit_app.command("list")
def audit_list(
    action: str | None = typer.Option(None, help="Filter by action, for example document.ingest."),
    outcome: str | None = typer.Option(None, help="Filter by outcome: success, denied, error."),
    limit: int = typer.Option(50, min=1, max=1000),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List audit events of the tenant, newest first. Needs the admin role."""
    from vlade_rag.core.application import ListAuditEvents

    async def go(rt: Any) -> Any:
        return await ListAuditEvents(rt.deps).execute(
            await _ctx(rt), action=action, outcome=outcome, limit=limit
        )

    events = _run(_with_runtime(go))
    if as_json:
        _print_json(
            [
                {
                    "created_at": e.created_at,
                    "action": e.action,
                    "outcome": e.outcome,
                    "interface": e.interface,
                    "resource": f"{e.resource_type}:{e.resource_id}" if e.resource_type else None,
                    "details": e.details,
                }
                for e in events
            ]
        )
        return
    for e in events:
        when = e.created_at.isoformat(timespec="seconds") if e.created_at else "-"
        typer.echo(f"{when}\t{e.outcome}\t{e.interface}\t{e.action}\t{e.resource_id or ''}")


@app.command()
def job(job_id: UUID) -> None:
    """Show an ingestion job."""
    from vlade_rag.core.application import GetIngestionStatus

    async def go(rt: Any) -> Any:
        return await GetIngestionStatus(rt.deps).execute(await _ctx(rt), job_id)

    j = _run(_with_runtime(go))
    _print_json(
        {
            "id": j.id,
            "status": j.status.value,
            "result": j.result,
            "error": j.error,
            "steps": [(s.name, s.status.value) for s in j.steps],
        }
    )


@app.command()
def search(
    knowledge_base: str,
    query: str,
    top_k: int = typer.Option(8, "--top-k"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Search chunks."""
    from vlade_rag.core.application import Search

    async def go(rt: Any) -> Any:
        return await Search(rt.deps).execute(
            await _ctx(rt), knowledge_base=knowledge_base, text=query, top_k=top_k
        )

    result = _run(_with_runtime(go))
    if as_json:
        _print_json(
            [
                {
                    "rank": i,
                    "score": r.score,
                    "document": r.chunk.document_title,
                    "page": r.chunk.page,
                    "section": r.chunk.section,
                    "text": r.chunk.text,
                }
                for i, r in enumerate(result.results, start=1)
            ]
        )
        return
    for i, r in enumerate(result.results, start=1):
        where = f" p.{r.chunk.page}" if r.chunk.page else ""
        typer.echo(f"[{i}] {r.chunk.document_title}{where} ({r.score:.4f})")
        typer.echo("    " + r.chunk.text[:300].replace("\n", " "))


@app.command()
def query(
    knowledge_base: str,
    question: str,
    stream: bool = typer.Option(False, help="Print the answer while it is generated."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Ask a question and print the answer with citations."""
    from vlade_rag.core.application import AnswerDelta, AnswerFinal, AnswerQuery

    async def go(rt: Any) -> Any:
        ctx = await _ctx(rt)
        use_case = AnswerQuery(rt.deps)
        if not stream:
            return await use_case.execute(ctx, knowledge_base=knowledge_base, question=question)
        final = None
        async for event in use_case.stream(ctx, knowledge_base=knowledge_base, question=question):
            if isinstance(event, AnswerDelta):
                sys.stdout.write(event.text)
                sys.stdout.flush()
            elif isinstance(event, AnswerFinal):
                final = event.answer
                if event.replaced:
                    sys.stdout.write("\n" + final.text)
        sys.stdout.write("\n")
        return final

    answer = _run(_with_runtime(go))
    if as_json:
        _print_json(
            {
                "answer": answer.text,
                "grounded": answer.grounded,
                "citations": [
                    {"index": c.index, "document": c.document_title, "page": c.page}
                    for c in answer.citations
                ],
            }
        )
        return
    if not stream:
        typer.echo(answer.text)
    for c in answer.citations:
        where = f", p.{c.page}" if c.page else ""
        typer.echo(f"  [{c.index}] {c.document_title}{where}")
