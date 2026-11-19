"""Row-Level Security is the second barrier (ADR-0012): it must hold even without app filters."""

from __future__ import annotations

from typing import Any

import pytest

from vlade_rag.core.application import CreateKnowledgeBase
from vlade_rag.core.domain import KnowledgeBaseConfig
from vlade_rag.core.domain.kb_config import EmbeddingsConfig

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


@pytest.fixture
async def pg(postgres_urls: tuple[str, str]) -> Any:
    from tests.conftest import _postgres_world

    world = await _postgres_world(postgres_urls[1])
    yield world
    await world.extra["db"].close()


async def test_unfiltered_queries_only_see_own_tenant(pg: Any) -> None:
    config = KnowledgeBaseConfig(
        embeddings=EmbeddingsConfig(provider="hashing", model="h", dimension=64)
    )
    await CreateKnowledgeBase(pg.deps).execute(pg.admin, slug="a", name="A", config=config)
    await CreateKnowledgeBase(pg.deps).execute(pg.other_admin, slug="b", name="B", config=config)
    db = pg.extra["db"]
    async with db.tenant(pg.admin) as conn:
        slugs = [r["slug"] for r in await conn.fetch("SELECT slug FROM knowledge_bases")]
        tenants = await conn.fetchval("SELECT count(*) FROM tenants")
    assert slugs == ["a"]
    assert tenants == 1


async def test_no_tenant_means_no_rows(pg: Any) -> None:
    db = pg.extra["db"]
    async with db.system() as conn:
        assert await conn.fetchval("SELECT count(*) FROM tenants") == 0
        assert await conn.fetchval("SELECT count(*) FROM api_keys") == 0


async def test_cannot_write_rows_of_another_tenant(pg: Any) -> None:
    import asyncpg

    db = pg.extra["db"]
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        async with db.tenant(pg.admin) as conn:
            await conn.execute(
                "INSERT INTO principals (id, tenant_id, name) VALUES (gen_random_uuid(), $1, 'x')",
                pg.other_admin.tenant_id,
            )


async def test_app_role_cannot_touch_migration_history(pg: Any) -> None:
    import asyncpg

    db = pg.extra["db"]
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        async with db.system() as conn:
            await conn.fetch("SELECT * FROM vlade_schema_migrations")


async def test_migrations_are_idempotent(postgres_urls: tuple[str, str]) -> None:
    from vlade_rag.knowledge.postgres.migrate import current_version, upgrade

    owner_url, app_url = postgres_urls
    assert await upgrade(owner_url, app_url) == []
    assert await current_version(owner_url) >= 1
