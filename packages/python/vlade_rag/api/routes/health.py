"""Health endpoints. ``/health/ready`` arrives in phase 1, with database checks."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
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
