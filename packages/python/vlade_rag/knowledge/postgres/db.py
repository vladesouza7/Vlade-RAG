"""Connection pool and tenant-scoped transactions (ADR-0012)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

from vlade_rag.core.domain import TenantContext


def asyncpg_dsn(url: str) -> str:
    """Accept SQLAlchemy-style URLs (``postgresql+asyncpg://``) as well as plain ones."""
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog", format="text"
    )
    await register_vector(conn)


class PostgresDatabase:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @classmethod
    async def connect(cls, url: str, *, min_size: int = 1, max_size: int = 10) -> PostgresDatabase:
        pool = await asyncpg.create_pool(
            asyncpg_dsn(url), min_size=min_size, max_size=max_size, init=_init_connection
        )
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    @asynccontextmanager
    async def tenant(self, ctx: TenantContext) -> AsyncIterator[asyncpg.Connection]:
        """A transaction where RLS restricts every query to ``ctx.tenant_id``."""
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(ctx.tenant_id))
            yield conn

    @asynccontextmanager
    async def system(self) -> AsyncIterator[asyncpg.Connection]:
        """A transaction without a tenant. RLS hides every tenant row; use definer functions."""
        async with self.pool.acquire() as conn, conn.transaction():
            yield conn

    async def fetchval(self, query: str, *args: Any) -> Any:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)
