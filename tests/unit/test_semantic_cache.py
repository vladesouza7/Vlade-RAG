"""Semantic cache over the Cache port (ADR-0030)."""

from __future__ import annotations

import pytest

from vlade_rag.core.application import SemanticCache, SemanticCacheSettings
from vlade_rag.core.domain import Role, TenantContext, uuid7
from vlade_rag.core.ports import Cache
from vlade_rag.knowledge.memory import MemoryCache, MemoryStore

pytestmark = pytest.mark.anyio


def make_ctx() -> TenantContext:
    return TenantContext(uuid7(), uuid7(), frozenset({Role.ADMIN}), "library")


@pytest.mark.parametrize("with_cache", [True, False])
async def test_similar_query_reuses_results(with_cache: bool) -> None:
    cache: Cache | None = MemoryCache(MemoryStore()) if with_cache else None
    semantic = SemanticCache(
        cache, SemanticCacheSettings(enabled=True, threshold=0.9, max_entries=4)
    )
    ctx = make_ctx()
    kb_id = uuid7()
    records = ({"id": str(uuid7()), "score": 0.8, "retriever": "dense"},)
    await semantic.store(ctx, kb_id, 1, [1.0, 0.0], records)
    found = await semantic.lookup(ctx, kb_id, 1, [0.99, 0.01])
    assert found == (records if with_cache else None)


async def test_threshold_and_epoch_separate_entries() -> None:
    semantic = SemanticCache(
        MemoryCache(MemoryStore()),
        SemanticCacheSettings(enabled=True, threshold=0.95, max_entries=4),
    )
    ctx = make_ctx()
    kb_id = uuid7()
    records = ({"id": str(uuid7()), "score": 0.8, "retriever": "dense"},)
    await semantic.store(ctx, kb_id, 1, [1.0, 0.0], records)
    assert await semantic.lookup(ctx, kb_id, 1, [0.5, 0.5]) is None
    assert await semantic.lookup(ctx, kb_id, 2, [1.0, 0.0]) is None


@pytest.mark.anyio
async def test_runtime_wires_the_semantic_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from vlade_rag.bootstrap import build_runtime
    from vlade_rag.core.config import Settings

    monkeypatch.setenv("VLADE_CACHE__SEMANTIC__ENABLED", "true")
    settings = Settings(
        storage={"backend": "memory"},  # type: ignore[arg-type]
        object_storage={"backend": "memory"},  # type: ignore[arg-type]
    )
    runtime = await build_runtime(settings, load_plugins=False)
    try:
        assert runtime.deps.semantic_cache.settings.enabled is True
        assert runtime.deps.semantic_cache.cache is runtime.deps.cache
    finally:
        await runtime.aclose()


async def test_tenant_isolation_and_bounded_entries() -> None:
    cache = MemoryCache(MemoryStore())
    semantic = SemanticCache(
        cache, SemanticCacheSettings(enabled=True, threshold=0.9, max_entries=2)
    )
    ctx, other = make_ctx(), make_ctx()
    kb_id = uuid7()
    for i in range(3):
        records = ({"id": str(uuid7()), "score": float(i), "retriever": "dense"},)
        await semantic.store(ctx, kb_id, 1, [1.0, i / 100], records)
    assert await semantic.lookup(other, kb_id, 1, [1.0, 0.0]) is None
    assert semantic.key(kb_id, 1).startswith("semsearch:")
