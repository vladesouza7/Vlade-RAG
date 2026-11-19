"""Health endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from vlade_rag import __version__
from vlade_rag.native import Backend, backend

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["ok"]
    version: str
    native_backend: Backend


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    """Report that the process is running. Does not check dependencies."""
    return LiveResponse(status="ok", version=__version__, native_backend=backend())


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Check the dependencies: database and object storage."""
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        return JSONResponse({"status": "starting"}, status_code=503)
    failures = await runtime.check()
    if failures:
        return JSONResponse({"status": "unavailable", "failures": failures}, status_code=503)
    return JSONResponse({"status": "ok"})
