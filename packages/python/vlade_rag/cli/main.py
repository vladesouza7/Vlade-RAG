"""Typer application for the ``vlade-rag`` command."""

from __future__ import annotations

import typer

from vlade_rag import __version__
from vlade_rag.core.config import get_settings
from vlade_rag.native import backend, engine_version

app = typer.Typer(name="vlade-rag", no_args_is_help=True, add_completion=False)
api_app = typer.Typer(help="REST API commands.", no_args_is_help=True)
app.add_typer(api_app, name="api")


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
    settings = get_settings()
    uvicorn.run(
        "vlade_rag.api.app:create_app",
        factory=True,
        host=host or settings.api.host,
        port=port or settings.api.port,
        log_level=settings.log_level.lower(),
    )
