"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from vlade_rag import __version__
from vlade_rag.api.routes import health
from vlade_rag.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API application."""
    settings = settings or get_settings()
    app = FastAPI(
        title="Vlade-RAG",
        version=__version__,
        docs_url="/docs" if settings.environment != "prod" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.include_router(health.router)
    return app
