"""Operations maintenance (roadmap 4.4): cleanup, job recovery and health checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from tests.conftest import World
from tests.integration.test_reindex import make_kb, reindex, submit
from vlade_rag.core.domain import NotFound, SpaceStatus, VersionChanged
from vlade_rag.core.domain.kb_config import EmbeddingsConfig
from vlade_rag.ops import OpsService

pytestmark = pytest.mark.anyio

NO_GRACE = {"retired_after": timedelta(0), "building_after": timedelta(0)}


async def test_cleanup_keeps_the_active_space(world: World) -> None:
    before = await make_kb(world)
    await reindex(world, embeddings={"model": "hashing-v2"}, confirm=True)
    assert await world.drain_jobs() == 1

    report = await OpsService(world.deps).cleanup(world.admin, **NO_GRACE)
    assert report.retired_spaces == 1
    after = await world.deps.repository.get_knowledge_base(world.admin, "vendas")
    assert after.active_embedding_space_id != before.active_embedding_space_id
    assert after.config.embeddings.model == "hashing-v2"
    space = await world.deps.repository.get_embedding_space(
        world.admin, after.active_embedding_space_id
    )
    chunks = await world.deps.repository.list_published_chunks(
        world.admin, after.id, after=None, limit=10_000
    )
    assert space.status is SpaceStatus.ACTIVE
    assert await world.deps.vector_index.count(world.admin, space, [c.id for c in chunks]) == len(
        chunks
    )


async def test_cleanup_keeps_building_spaces_during_a_reindex(world: World) -> None:
    await make_kb(world)
    await reindex(world, embeddings={"model": "hashing-v2"}, confirm=True)
    orphan = await world.deps.repository.create_embedding_space(
        world.admin,
        EmbeddingsConfig(provider="hashing", model="hashing-v2", dimension=64),
    )
    service = OpsService(world.deps)

    report = await service.cleanup(world.admin, **NO_GRACE)
    assert report.building_spaces == 0  # a reindex job is pending for this tenant
    assert await world.deps.repository.get_embedding_space(world.admin, orphan.id)

    assert await world.drain_jobs() == 1
    report = await service.cleanup(world.admin, **NO_GRACE)
    assert report.building_spaces == 1
    with pytest.raises(NotFound):
        await world.deps.repository.get_embedding_space(world.admin, orphan.id)


async def test_cleanup_deletes_old_superseded_versions(world: World) -> None:
    await make_kb(world)
    await submit(world, "garantia.md", "# Garantia\n\nTexto novo da garantia.")
    await world.drain_jobs()

    repo = world.deps.repository
    kb = await repo.get_knowledge_base(world.admin, "vendas")
    assert await repo.count_superseded_versions(world.admin, datetime.now(UTC)) >= 1
    report = await OpsService(world.deps).cleanup(world.admin, **NO_GRACE)
    assert report.versions >= 1
    assert await repo.count_superseded_versions(world.admin, datetime.now(UTC)) == 0
    assert len(await repo.list_current_versions(world.admin, kb.id)) == 3


async def test_publish_refuses_a_stale_expected_version(world: World) -> None:
    """A full reindex cannot publish its old version over a newer one."""
    await make_kb(world)
    first = await submit(world, "garantia.md", "# Garantia\n\nTexto antigo.")
    await world.drain_jobs()
    kb = await world.deps.repository.get_knowledge_base(world.admin, "vendas")
    versions = await world.deps.repository.list_current_versions(world.admin, kb.id)
    old = next(version for document, version in versions if document.title == "garantia.md")

    await submit(world, "garantia.md", "# Garantia\n\nTexto novo.")
    await world.drain_jobs()
    with pytest.raises(VersionChanged):
        await world.deps.repository.publish_version(
            world.admin, UUID(str(first.job.input["version_id"])), expected_version_id=old.id
        )


async def test_recover_jobs_and_health(world: World) -> None:
    service = OpsService(world.deps)
    assert await service.recover_jobs() == 0

    async def fail() -> None:
        raise RuntimeError("probe failed")

    other = OpsService(world.deps, checks={"database": fail})
    report = await other.health()
    assert not report.ok and report.failures == ("database",)
