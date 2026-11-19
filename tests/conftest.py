"""Shared fixtures.

``world`` runs every scenario twice: with in-memory adapters and with PostgreSQL. The PostgreSQL
run needs ``VLADE_TEST_DATABASE_URL`` (a superuser URL); without it, the run is skipped.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import pytest

from vlade_rag.core.application import Dependencies, RunIngestionJob
from vlade_rag.core.domain import Role, TenantContext
from vlade_rag.core.ports import JobQueue, TenantDirectory
from vlade_rag.embeddings.hashing import HashingEmbeddingProvider
from vlade_rag.generation.prompts import BuiltinPromptRegistry
from vlade_rag.generation.providers.extractive import ExtractiveLLM
from vlade_rag.ingestion.chunking import NativeChunker, NativeTextNormalizer
from vlade_rag.ingestion.parsers.basic import basic_parsers
from vlade_rag.knowledge.memory import MemoryStore, memory_adapters
from vlade_rag.retrieval.fusion import RRFFusion

TEST_DB_ENV = "VLADE_TEST_DATABASE_URL"
NOT_FOUND_PT = "Não encontrei essa informação nas fontes disponíveis."


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _common(**ports: Any) -> Dependencies:
    embedder = HashingEmbeddingProvider(dimension=64)
    llm = ExtractiveLLM(not_found=NOT_FOUND_PT)
    return Dependencies(
        parsers=basic_parsers(),
        normalizer=NativeTextNormalizer(),
        chunker=NativeChunker(),
        fusion=RRFFusion(),
        prompts=BuiltinPromptRegistry(),
        embeddings=lambda cfg: embedder,
        llms=lambda cfg: llm,
        **ports,
    )


@dataclass
class World:
    backend: str
    deps: Dependencies
    tenants: TenantDirectory
    job_queue: JobQueue
    admin: TenantContext
    reader: TenantContext
    other_admin: TenantContext
    objects: MemoryStore
    extra: dict[str, Any] = field(default_factory=dict)

    async def drain_jobs(self) -> int:
        """Run every pending job, like the worker does."""
        runner = RunIngestionJob(self.deps)
        count = 0
        while (claimed := await self.job_queue.claim("test-worker", 60)) is not None:
            await runner.execute(claimed)
            count += 1
        return count

    def object_keys(self, ctx: TenantContext) -> list[str]:
        return list(self.objects.data(ctx).objects)

    async def audit_actions(self, ctx: TenantContext) -> list[tuple[str, str]]:
        if self.backend == "memory":
            return [(e.action, e.outcome) for e in self.extra["store"].data(ctx).audit]
        async with self.extra["db"].tenant(ctx) as conn:
            rows = await conn.fetch("SELECT action, outcome FROM audit_events ORDER BY created_at")
        return [(r["action"], r["outcome"]) for r in rows]


async def _make_contexts(tenants: TenantDirectory) -> tuple[TenantContext, ...]:
    suffix = secrets.token_hex(4)
    acme = await tenants.create_tenant(f"acme-{suffix}", "ACME")
    globex = await tenants.create_tenant(f"globex-{suffix}", "Globex")
    keys = [
        await tenants.issue_api_key(acme.id, principal_name="admin", roles=frozenset({Role.ADMIN})),
        await tenants.issue_api_key(
            acme.id, principal_name="reader", roles=frozenset({Role.READER})
        ),
        await tenants.issue_api_key(
            globex.id, principal_name="admin", roles=frozenset({Role.ADMIN})
        ),
    ]
    return tuple([await tenants.authenticate(k.key, interface="library") for k in keys])


async def _memory_world() -> World:
    adapters = memory_adapters()
    deps = _common(
        repository=adapters.repository,
        vector_index=adapters.vector_index,
        lexical_indexes={"lexical": adapters.lexical_index},
        object_storage=adapters.object_storage,
        job_queue=adapters.job_queue,
        audit_log=adapters.audit_log,
        cache=adapters.cache,
    )
    admin, reader, other = await _make_contexts(adapters.tenants)
    return World(
        "memory",
        deps,
        adapters.tenants,
        adapters.job_queue,
        admin,
        reader,
        other,
        adapters.store,
        {"store": adapters.store},
    )


def _with_database(
    url: str, database: str, user: str | None = None, password: str | None = None
) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc.split("@", 1)[-1]
    netloc = f"{user}:{password}@{netloc}" if user is not None else parts.netloc
    return urlunsplit((parts.scheme, netloc, f"/{database}", "", ""))


@pytest.fixture(scope="session")
def postgres_urls() -> Any:
    """Create a throwaway database, run the migrations, yield (owner_url, app_url)."""
    url = os.environ.get(TEST_DB_ENV)
    if not url:
        pytest.skip(f"{TEST_DB_ENV} is not set")
    import asyncio

    import asyncpg

    from vlade_rag.knowledge.postgres.migrate import upgrade

    database = f"vlade_test_{secrets.token_hex(4)}"
    app_password = secrets.token_hex(12)
    owner_url = _with_database(url, database)
    app_url = _with_database(url, database, "vlade_app_test", app_password)

    async def _setup() -> None:
        conn = await asyncpg.connect(url)
        await conn.execute(f'CREATE DATABASE "{database}"')
        await conn.close()
        await upgrade(owner_url, app_url)

    async def _teardown() -> None:
        conn = await asyncpg.connect(url)
        await conn.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        await conn.close()

    # The fixture may be requested from inside a running event loop: use a separate thread.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, _setup()).result()
    yield owner_url, app_url
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, _teardown()).result()


async def _postgres_world(app_url: str) -> World:
    from vlade_rag.knowledge.memory import MemoryCache, MemoryObjectStorage
    from vlade_rag.knowledge.postgres import (
        PgVectorIndex,
        PostgresAuditLog,
        PostgresDatabase,
        PostgresJobQueue,
        PostgresKnowledgeRepository,
        PostgresTenantDirectory,
        TsvectorLexicalIndex,
    )

    db = await PostgresDatabase.connect(app_url, min_size=1, max_size=4)
    objects = MemoryStore()
    queue = PostgresJobQueue(db)
    deps = _common(
        repository=PostgresKnowledgeRepository(db),
        vector_index=PgVectorIndex(db),
        lexical_indexes={"lexical": TsvectorLexicalIndex(db)},
        object_storage=MemoryObjectStorage(objects),
        job_queue=queue,
        audit_log=PostgresAuditLog(db),
        cache=MemoryCache(objects),
    )
    tenants = PostgresTenantDirectory(db, pepper="test-pepper")
    admin, reader, other = await _make_contexts(tenants)
    return World("postgres", deps, tenants, queue, admin, reader, other, objects, {"db": db})


@pytest.fixture(
    params=["memory", pytest.param("postgres", marks=pytest.mark.integration)],
)
async def world(request: pytest.FixtureRequest) -> AsyncIterator[World]:
    if request.param == "memory":
        yield await _memory_world()
        return
    _, app_url = request.getfixturevalue("postgres_urls")
    w = await _postgres_world(app_url)
    try:
        yield w
    finally:
        await w.extra["db"].close()


def doc_id(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))
