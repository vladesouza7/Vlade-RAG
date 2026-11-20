"""Contract of the ``Cache`` and ``RateLimiter`` ports: memory and Valkey run the same tests.

The Valkey run needs ``VLADE_TEST_VALKEY_URL`` (for example ``redis://localhost:6379/0``).
Every test uses new tenant ids, so it never reads keys of another test.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import pytest

from vlade_rag.core.domain import Role, TenantContext, uuid7
from vlade_rag.core.ports import Cache, RateLimiter
from vlade_rag.knowledge.memory import MemoryCache, MemoryRateLimiter, MemoryStore

pytestmark = pytest.mark.anyio

VALKEY_ENV = "VLADE_TEST_VALKEY_URL"


@dataclass
class Backend:
    cache: Cache
    limiter: RateLimiter


def make_ctx() -> TenantContext:
    return TenantContext(uuid7(), uuid7(), frozenset({Role.ADMIN}), "library")


@pytest.fixture(params=["memory", pytest.param("valkey", marks=pytest.mark.integration)])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    if request.param == "memory":
        yield Backend(MemoryCache(MemoryStore()), MemoryRateLimiter())
        return
    url = os.environ.get(VALKEY_ENV)
    if not url:
        pytest.skip(f"{VALKEY_ENV} is not set")
    pytest.importorskip("redis")
    from vlade_rag.knowledge.valkey import ValkeyCache, ValkeyRateLimiter, connect

    client = connect(url)
    try:
        yield Backend(ValkeyCache(client), ValkeyRateLimiter(client))
    finally:
        await client.aclose()


# ---------------------------------------------------------------- cache


async def test_cache_round_trip(backend: Backend) -> None:
    ctx = make_ctx()
    assert await backend.cache.get(ctx, "k") is None
    await backend.cache.set(ctx, "k", b"value", 60)
    assert await backend.cache.get(ctx, "k") == b"value"
    await backend.cache.set(ctx, "k", b"newer", 60)
    assert await backend.cache.get(ctx, "k") == b"newer"


async def test_cache_entry_expires(backend: Backend) -> None:
    ctx = make_ctx()
    await backend.cache.set(ctx, "k", b"v", 1)
    await asyncio.sleep(1.2)
    assert await backend.cache.get(ctx, "k") is None


async def test_cache_is_tenant_scoped(backend: Backend) -> None:
    a, b = make_ctx(), make_ctx()
    await backend.cache.set(a, "k", b"secret-of-a", 60)
    assert await backend.cache.get(b, "k") is None
    await backend.cache.set(b, "k", b"b", 60)
    assert await backend.cache.get(a, "k") == b"secret-of-a"
    assert await backend.cache.delete_prefix(b, "") == 1  # only the keys of b
    assert await backend.cache.get(a, "k") == b"secret-of-a"


async def test_delete_prefix_removes_only_that_prefix(backend: Backend) -> None:
    ctx = make_ctx()
    for key in ("search:1:a", "search:1:b", "search:2:a", "emb:x"):
        await backend.cache.set(ctx, key, b"v", 60)
    assert await backend.cache.delete_prefix(ctx, "search:1:") == 2
    assert await backend.cache.get(ctx, "search:1:a") is None
    assert await backend.cache.get(ctx, "search:2:a") == b"v"
    assert await backend.cache.get(ctx, "emb:x") == b"v"
    assert await backend.cache.delete_prefix(ctx, "nothing:") == 0


async def test_delete_prefix_does_not_treat_glob_characters_as_wildcards(backend: Backend) -> None:
    ctx = make_ctx()
    await backend.cache.set(ctx, "a*b", b"1", 60)
    await backend.cache.set(ctx, "axb", b"2", 60)
    assert await backend.cache.delete_prefix(ctx, "a*") == 1
    assert await backend.cache.get(ctx, "axb") == b"2"


# ---------------------------------------------------------------- rate limiter


async def test_bucket_allows_capacity_then_denies(backend: Backend) -> None:
    tenant = uuid7()
    for i in range(3):
        decision = await backend.limiter.take(tenant, "k", capacity=3, refill_per_second=0.01)
        assert decision.allowed, i
        assert decision.retry_after_seconds == 0
    denied = await backend.limiter.take(tenant, "k", capacity=3, refill_per_second=0.01)
    assert not denied.allowed
    assert 50 < denied.retry_after_seconds <= 100  # one token at 0.01 per second
    assert denied.remaining < 1


async def test_bucket_refills_over_time(backend: Backend) -> None:
    tenant = uuid7()
    # One token every 200 ms: a short pause under load cannot refill the bucket by accident.
    for _ in range(2):
        await backend.limiter.take(tenant, "k", capacity=2, refill_per_second=5)
    assert not (await backend.limiter.take(tenant, "k", capacity=2, refill_per_second=5)).allowed
    await asyncio.sleep(0.45)  # more than two tokens, capped at the capacity
    assert (await backend.limiter.take(tenant, "k", capacity=2, refill_per_second=5)).allowed


async def test_bucket_cost_and_isolation(backend: Backend) -> None:
    tenant, other = uuid7(), uuid7()
    big = await backend.limiter.take(tenant, "k", capacity=5, refill_per_second=0.01, cost=5)
    assert big.allowed and big.remaining < 1
    assert not (await backend.limiter.take(tenant, "k", capacity=5, refill_per_second=0.01)).allowed
    # Another key of the same tenant and the same key of another tenant have their own bucket.
    assert (await backend.limiter.take(tenant, "k2", capacity=5, refill_per_second=0.01)).allowed
    assert (await backend.limiter.take(other, "k", capacity=5, refill_per_second=0.01)).allowed


async def test_daily_counter(backend: Backend) -> None:
    tenant, other = uuid7(), uuid7()
    assert await backend.limiter.count_day(tenant, "requests", increment=False) == 0
    assert await backend.limiter.count_day(tenant, "requests", increment=True) == 1
    assert await backend.limiter.count_day(tenant, "requests", increment=True) == 2
    assert await backend.limiter.count_day(tenant, "requests", increment=False) == 2
    assert await backend.limiter.count_day(other, "requests", increment=False) == 0
    assert await backend.limiter.count_day(tenant, "other-key", increment=False) == 0


# ---------------------------------------------------------------- memory specifics


async def test_memory_limiter_with_a_fake_clock() -> None:
    now = [1_000.0]
    limiter = MemoryRateLimiter(clock=lambda: now[0])
    tenant: UUID = uuid7()
    assert (await limiter.take(tenant, "k", capacity=1, refill_per_second=1)).allowed
    denied = await limiter.take(tenant, "k", capacity=1, refill_per_second=1)
    assert not denied.allowed and denied.retry_after_seconds == pytest.approx(1.0)
    now[0] += 1.0
    assert (await limiter.take(tenant, "k", capacity=1, refill_per_second=1)).allowed


async def test_memory_daily_counter_resets_on_the_next_utc_day() -> None:
    now = [86_400.0 * 10 + 100]  # day 10, shortly after midnight UTC
    limiter = MemoryRateLimiter(clock=lambda: now[0])
    tenant = uuid7()
    assert await limiter.count_day(tenant, "requests", increment=True) == 1
    now[0] += 86_400  # next day
    assert await limiter.count_day(tenant, "requests", increment=False) == 0
    assert await limiter.count_day(tenant, "requests", increment=True) == 1


# ---------------------------------------------------------------- Valkey is down


async def test_valkey_failure_does_not_fail_the_request() -> None:
    pytest.importorskip("redis")
    from vlade_rag.knowledge.valkey import ValkeyCache, ValkeyRateLimiter, connect

    client = connect("redis://127.0.0.1:1/0")  # nothing listens on port 1
    try:
        ctx = make_ctx()
        cache = ValkeyCache(client)
        await cache.set(ctx, "k", b"v", 60)  # dropped, no error
        assert await cache.get(ctx, "k") is None  # a miss
        assert await cache.delete_prefix(ctx, "k") == 0
        limiter = ValkeyRateLimiter(client)
        decision = await limiter.take(ctx.tenant_id, "k", capacity=1, refill_per_second=1)
        assert decision.allowed  # fail open
        assert await limiter.count_day(ctx.tenant_id, "requests", increment=True) == 0
    finally:
        await client.aclose()
