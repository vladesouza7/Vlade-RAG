"""Valkey (or Redis) adapters: ``Cache`` and ``RateLimiter`` (docs/adr/0007-cache-valkey.md).

Every key starts with the tenant id, so a tenant never reads or counts the keys of another one.
A failure of the server is not a failure of the request:

- the cache treats it as a miss and drops the write;
- the rate limiter lets the request pass ("fail open") and logs a warning.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from vlade_rag.core.domain import TenantContext
from vlade_rag.core.ports import RateDecision

logger = logging.getLogger(__name__)

# KEYS[1] bucket; ARGV: capacity, refill per second, cost. Returns {allowed, tokens, retry}.
# The time comes from the server, so processes with different clocks share one bucket.
_BUCKET_SCRIPT = """
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
tokens = math.min(capacity, tokens + math.max(now - ts, 0) * refill)
local allowed = 0
local retry = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry = (cost - tokens) / refill
end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / refill) + 1)
return {allowed, tostring(tokens), tostring(retry)}
"""

_DAY_SECONDS = 2 * 24 * 3600  # a counter outlives its UTC day, then expires


def connect(url: str) -> Redis:
    """Create a client. The connection opens on the first command."""
    return Redis.from_url(url)


def _glob_escape(text: str) -> str:
    return "".join("\\" + c if c in "*?[]\\" else c for c in text)


class ValkeyCache:
    def __init__(self, client: Redis) -> None:
        self.client = client

    @staticmethod
    def _key(ctx: TenantContext, key: str) -> str:
        return f"{ctx.tenant_id}/{key}"

    async def get(self, ctx: TenantContext, key: str) -> bytes | None:
        try:
            value: Any = await self.client.get(self._key(ctx, key))
        except RedisError as exc:
            logger.warning("Cache read failed; treated as a miss: %s", exc)
            return None
        return None if value is None else bytes(value)

    async def set(self, ctx: TenantContext, key: str, value: bytes, ttl_seconds: int) -> None:
        try:
            await self.client.set(self._key(ctx, key), value, ex=max(int(ttl_seconds), 1))
        except RedisError as exc:
            logger.warning("Cache write failed; the value is not cached: %s", exc)

    async def delete_prefix(self, ctx: TenantContext, prefix: str) -> int:
        pattern = _glob_escape(self._key(ctx, prefix)) + "*"
        deleted = 0
        try:
            batch: list[bytes] = []
            async for found in self.client.scan_iter(match=pattern, count=500):
                batch.append(found)
                if len(batch) >= 500:
                    deleted += int(await self.client.unlink(*batch))
                    batch.clear()
            if batch:
                deleted += int(await self.client.unlink(*batch))
        except RedisError as exc:
            logger.warning("Cache delete failed: %s", exc)
        return deleted


class ValkeyRateLimiter:
    def __init__(self, client: Redis) -> None:
        self.client = client
        self._bucket = client.register_script(_BUCKET_SCRIPT)

    async def take(
        self,
        tenant_id: UUID,
        key: str,
        *,
        capacity: int,
        refill_per_second: float,
        cost: int = 1,
    ) -> RateDecision:
        try:
            result: Any = await self._bucket(
                keys=[f"rl:{tenant_id}/{key}"], args=[capacity, refill_per_second, cost]
            )
        except RedisError as exc:
            logger.warning("Rate limiter unavailable; the request passes: %s", exc)
            return RateDecision(allowed=True, retry_after_seconds=0.0, remaining=float(capacity))
        return RateDecision(
            allowed=int(result[0]) == 1,
            remaining=float(result[1]),
            retry_after_seconds=float(result[2]),
        )

    async def count_day(self, tenant_id: UUID, key: str, *, increment: bool) -> int:
        day = datetime.now(UTC).strftime("%Y%m%d")
        slot = f"rld:{tenant_id}/{key}:{day}"
        try:
            if increment:
                async with self.client.pipeline(transaction=True) as pipe:
                    pipe.incr(slot)
                    pipe.expire(slot, _DAY_SECONDS)
                    count: Any = (await pipe.execute())[0]
                return int(count)
            value: Any = await self.client.get(slot)
        except RedisError as exc:
            logger.warning("Rate limiter unavailable; the count is 0: %s", exc)
            return 0
        return 0 if value is None else int(value)
