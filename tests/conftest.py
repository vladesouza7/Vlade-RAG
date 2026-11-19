from __future__ import annotations

from dataclasses import dataclass

import pytest

from vlade_rag.core.application import Dependencies, RunIngestionJob
from vlade_rag.core.domain import Role, TenantContext
from vlade_rag.embeddings.hashing import HashingEmbeddingProvider
from vlade_rag.generation.prompts import BuiltinPromptRegistry
from vlade_rag.generation.providers.extractive import ExtractiveLLM
from vlade_rag.ingestion.chunking import NativeChunker, NativeTextNormalizer
from vlade_rag.ingestion.parsers.basic import basic_parsers
from vlade_rag.knowledge.memory import MemoryAdapters, memory_adapters
from vlade_rag.retrieval.fusion import RRFFusion


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def build_memory_deps(adapters: MemoryAdapters) -> Dependencies:
    embedder = HashingEmbeddingProvider(dimension=64)
    llm = ExtractiveLLM(not_found="Não encontrei essa informação nas fontes disponíveis.")
    return Dependencies(
        repository=adapters.repository,
        vector_index=adapters.vector_index,
        lexical_indexes={"lexical": adapters.lexical_index},
        object_storage=adapters.object_storage,
        job_queue=adapters.job_queue,
        audit_log=adapters.audit_log,
        parsers=basic_parsers(),
        normalizer=NativeTextNormalizer(),
        chunker=NativeChunker(),
        fusion=RRFFusion(),
        prompts=BuiltinPromptRegistry(),
        embeddings=lambda cfg: embedder,
        llms=lambda cfg: llm,
        cache=adapters.cache,
    )


@dataclass
class World:
    adapters: MemoryAdapters
    deps: Dependencies
    admin: TenantContext
    reader: TenantContext
    other_admin: TenantContext

    async def drain_jobs(self) -> int:
        """Run every pending job, like the worker does."""
        runner = RunIngestionJob(self.deps)
        count = 0
        while (claimed := await self.adapters.job_queue.claim("test-worker", 60)) is not None:
            await runner.execute(claimed)
            count += 1
        return count


@pytest.fixture
async def world() -> World:
    adapters = memory_adapters()
    tenants = adapters.tenants
    acme = await tenants.create_tenant("acme", "ACME")
    globex = await tenants.create_tenant("globex", "Globex")
    admin_key = await tenants.issue_api_key(
        acme.id, principal_name="admin", roles=frozenset({Role.ADMIN})
    )
    reader_key = await tenants.issue_api_key(
        acme.id, principal_name="reader", roles=frozenset({Role.READER})
    )
    other_key = await tenants.issue_api_key(
        globex.id, principal_name="admin", roles=frozenset({Role.ADMIN})
    )
    return World(
        adapters=adapters,
        deps=build_memory_deps(adapters),
        admin=await tenants.authenticate(admin_key.key, interface="library"),
        reader=await tenants.authenticate(reader_key.key, interface="library"),
        other_admin=await tenants.authenticate(other_key.key, interface="library"),
    )
