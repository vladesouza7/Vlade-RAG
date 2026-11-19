"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from vlade_rag import __version__
from vlade_rag.api.routes import health, v1
from vlade_rag.api.schemas import Problem
from vlade_rag.bootstrap import Runtime, build_runtime
from vlade_rag.core.config import Settings, get_settings
from vlade_rag.core.domain import VladeError

logger = logging.getLogger(__name__)
PROBLEM_JSON = "application/problem+json"


def _problem(status: int, title: str, detail: str, code: str, retryable: bool) -> JSONResponse:
    body = Problem(title=title, status=status, detail=detail, code=code, retryable=retryable)
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(
        body.model_dump(), status_code=status, media_type=PROBLEM_JSON, headers=headers
    )


def create_app(settings: Settings | None = None, runtime: Runtime | None = None) -> FastAPI:
    """Build the API. Without ``runtime``, the lifespan builds one from ``settings``."""
    settings = settings or get_settings()

    from vlade_rag.observability.opentelemetry import setup_telemetry

    tracer = setup_telemetry(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        rt = runtime or await build_runtime(settings, tracer=tracer)
        app.state.runtime = rt
        worker_task: asyncio.Task[None] | None = None
        if settings.api.embedded_worker:
            from vlade_rag.ingestion.worker import Worker

            worker = Worker(rt, worker_id="api-embedded")
            worker_task = asyncio.create_task(worker.run())
        try:
            yield
        finally:
            if worker_task is not None:
                worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await worker_task
            if runtime is None:
                await rt.aclose()

    app = FastAPI(
        title="Vlade-RAG",
        version=__version__,
        docs_url="/docs" if settings.environment != "prod" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    if runtime is not None:
        app.state.runtime = runtime

    @app.exception_handler(VladeError)
    async def vlade_error(request: Request, exc: VladeError) -> JSONResponse:
        return _problem(exc.http_status, type(exc).__name__, exc.message, exc.code, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return _problem(422, "InvalidArgument", detail, "invalid_argument", False)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return _problem(500, "InternalError", "Unexpected error.", "internal", True)

    @app.middleware("http")
    async def telemetry(request: Request, call_next: Any) -> Any:
        if request.url.path.startswith("/health"):
            return await call_next(request)
        route = request.url.path
        started = time.perf_counter()
        with tracer.span(
            f"{request.method} {route}",
            {"http.request.method": request.method, "url.path": route},
        ) as span:
            response = await call_next(request)
            span.set_attribute("http.response.status_code", response.status_code)
        _record_duration(request.method, response.status_code, time.perf_counter() - started)
        return response

    app.include_router(health.router)
    app.include_router(v1.router)
    return app


def _record_duration(method: str, status: int, seconds: float) -> None:
    try:
        from opentelemetry import metrics
    except ImportError:
        return
    global _DURATION
    if _DURATION is None:
        _DURATION = metrics.get_meter("vlade_rag").create_histogram(
            "vlade_request_duration_seconds", unit="s", description="HTTP request duration"
        )
    _DURATION.record(seconds, {"interface": "api", "method": method, "status": status})


_DURATION: Any = None
