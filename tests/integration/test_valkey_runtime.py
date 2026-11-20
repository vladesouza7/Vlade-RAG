"""The runtime uses Valkey when ``VLADE_CACHE__URL`` is set."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("redis")

from vlade_rag.bootstrap import build_runtime
from vlade_rag.core.application import EnforceRequestLimits
from vlade_rag.core.config import Settings
from vlade_rag.core.domain import RateLimited, Role
from vlade_rag.knowledge.memory import MemoryCache, MemoryRateLimiter
from vlade_rag.knowledge.valkey import ValkeyCache, ValkeyRateLimiter

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


def _settings(**cache: object) -> Settings:
    return Settings(
        storage={"backend": "memory"},  # type: ignore[arg-type]
        object_storage={"backend": "memory"},  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
        limits={"rate_per_key_per_minute": 2, "rate_per_tenant_per_minute": 0},  # type: ignore[arg-type]
    )


async def test_without_a_url_the_runtime_uses_memory() -> None:
    rt = await build_runtime(_settings(), load_plugins=False)
    try:
        assert isinstance(rt.deps.cache, MemoryCache)
        assert isinstance(rt.deps.rate_limiter, MemoryRateLimiter)
        assert "cache" not in rt.checks
    finally:
        await rt.aclose()


async def test_with_a_url_the_runtime_uses_valkey() -> None:
    url = os.environ.get("VLADE_TEST_VALKEY_URL")
    if not url:
        pytest.skip("VLADE_TEST_VALKEY_URL is not set")
    rt = await build_runtime(_settings(url=url), load_plugins=False)
    try:
        assert isinstance(rt.deps.cache, ValkeyCache)
        assert isinstance(rt.deps.rate_limiter, ValkeyRateLimiter)
        await rt.checks["cache"]()  # the readiness check pings the server

        tenant = await rt.tenants.create_tenant("valkey-rt", "Valkey")
        key = await rt.tenants.issue_api_key(
            tenant.id, principal_name="p", roles=frozenset({Role.READER})
        )
        ctx = await rt.tenants.authenticate(key.key, interface="api")
        limits = EnforceRequestLimits(rt.deps)
        await limits.execute(ctx)
        await limits.execute(ctx)
        with pytest.raises(RateLimited) as caught:
            await limits.execute(ctx)
        assert caught.value.details["retry_after_seconds"] >= 1
    finally:
        await rt.aclose()
