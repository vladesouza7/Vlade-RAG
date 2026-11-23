"""Wiring of the optional Qdrant vector index (ADR-0004)."""

from __future__ import annotations

import pytest

from vlade_rag.bootstrap import build_runtime
from vlade_rag.core.config import Settings
from vlade_rag.knowledge.memory import MemoryVectorIndex

pytest.importorskip("qdrant_client")


@pytest.mark.anyio
async def test_pgvector_remains_the_default() -> None:
    settings = Settings(storage={"backend": "memory"}, object_storage={"backend": "memory"})  # type: ignore[arg-type]
    runtime = await build_runtime(settings, load_plugins=False)
    try:
        assert isinstance(runtime.deps.vector_index, MemoryVectorIndex)
    finally:
        await runtime.aclose()


@pytest.mark.anyio
async def test_qdrant_backend_is_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    from vlade_rag.knowledge.qdrant import QdrantVectorIndex

    monkeypatch.setenv("VLADE_VECTOR_INDEX__BACKEND", "qdrant")
    settings = Settings(storage={"backend": "memory"}, object_storage={"backend": "memory"})  # type: ignore[arg-type]
    runtime = await build_runtime(settings, load_plugins=False)
    try:
        assert isinstance(runtime.deps.vector_index, QdrantVectorIndex)
        assert "vector_index" in runtime.checks
    finally:
        await runtime.aclose()
