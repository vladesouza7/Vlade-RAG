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
from vlade_rag.core.domain import KnowledgeBaseConfig, Role, TenantContext, VladeError
from vlade_rag.native import backend, engine_version

app = typer.Typer(name="vlade-rag", no_args_is_help=True, add_completion=False)
api_app = typer.Typer(help="REST API commands.", no_args_is_help=True)
db_app = typer.Typer(help="Database commands (owner credentials).", no_args_is_help=True)
tenant_app = typer.Typer(help="Tenant administration.", no_args_is_help=True)
key_app = typer.Typer(help="API key administration.", no_args_is_help=True)
kb_app = typer.Typer(help="Knowledge bases.", no_args_is_help=True)
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


def _load_config(path: Path | None) -> KnowledgeBaseConfig:
    if path is None:
        return KnowledgeBaseConfig()
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            typer.echo("YAML needs PyYAML. Use a .json file instead.", err=True)
            raise typer.Exit(2) from exc
        return KnowledgeBaseConfig.model_validate(yaml.safe_load(text))
    return KnowledgeBaseConfig.model_validate_json(text)


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
