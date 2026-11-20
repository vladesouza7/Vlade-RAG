"""Quotas and audit log. Runs with in-memory adapters and with PostgreSQL (see ``world``)."""

from __future__ import annotations

from uuid import UUID

import pytest

from tests.conftest import World
from vlade_rag.core.application import (
    CreateKnowledgeBase,
    GetUsage,
    ListAuditEvents,
    SubmitIngestion,
    SubmitResult,
)
from vlade_rag.core.domain import (
    InvalidArgument,
    KnowledgeBaseConfig,
    NotFound,
    PermissionDenied,
    QuotaExceeded,
    RawDocument,
    Role,
    TenantQuotas,
    TenantUsage,
    Unauthenticated,
)
from vlade_rag.core.domain.kb_config import ChunkingConfig, EmbeddingsConfig

pytestmark = pytest.mark.anyio


def kb_config() -> KnowledgeBaseConfig:
    return KnowledgeBaseConfig(
        chunking=ChunkingConfig(strategy="markdown", max_tokens=40, overlap_tokens=5),
        embeddings=EmbeddingsConfig(provider="hashing", model="hashing-v1", dimension=64),
    )


@pytest.fixture
async def kb(world: World) -> World:
    await CreateKnowledgeBase(world.deps).execute(
        world.admin, slug="docs", name="Docs", config=kb_config()
    )
    return world


async def submit(
    world: World, name: str, text: str, *, external_id: str | None = None
) -> SubmitResult:
    return await SubmitIngestion(world.deps).execute(
        world.admin,
        knowledge_base="docs",
        raw=RawDocument(filename=name, mime_type="text/markdown", data=text.encode()),
        external_id=external_id or name,
    )


async def audit(world: World, action: str, outcome: str | None = None) -> list[str]:
    events = await ListAuditEvents(world.deps).execute(
        world.admin, action=action, outcome=outcome, limit=50
    )
    return [e.outcome for e in events]


# ---------------------------------------------------------------- domain


def test_quotas_round_trip_and_validation() -> None:
    assert TenantQuotas.from_settings({}) == TenantQuotas()
    quotas = TenantQuotas(documents=3, bytes=1000)
    assert TenantQuotas.from_settings({"quotas": quotas.to_settings()}) == quotas
    assert TenantQuotas(documents=0).to_settings() == {"documents": 0}
    with pytest.raises(InvalidArgument):
        TenantQuotas(documents=-1)
    with pytest.raises(InvalidArgument):
        TenantQuotas.from_settings({"quotas": {"bytes": "10"}})


def test_check_submit_limits() -> None:
    quotas = TenantQuotas(documents=2, bytes=100)
    usage = TenantUsage(documents=2, bytes=50)
    quotas.check_submit(usage, new_document=False, added_bytes=50)  # update, fits
    with pytest.raises(QuotaExceeded):
        quotas.check_submit(usage, new_document=True, added_bytes=1)
    with pytest.raises(QuotaExceeded):
        quotas.check_submit(usage, new_document=False, added_bytes=51)
    TenantQuotas().check_submit(usage, new_document=True, added_bytes=10**9)  # unlimited


# ---------------------------------------------------------------- quotas


async def test_no_quota_means_unlimited(kb: World) -> None:
    view = await GetUsage(kb.deps).execute(kb.admin)
    assert view.quotas == TenantQuotas()
    assert view.usage == TenantUsage(0, 0)
    for i in range(3):
        await submit(kb, f"d{i}.md", f"# Doc {i}\n\ntexto {i}")


async def test_document_quota(kb: World) -> None:
    await kb.tenants.set_quotas(kb.admin.tenant_id, TenantQuotas(documents=2))
    await submit(kb, "a.md", "# A\n\num")
    await submit(kb, "b.md", "# B\n\ndois")
    with pytest.raises(QuotaExceeded):
        await submit(kb, "c.md", "# C\n\ntres")
    # Updating an existing document does not add a document.
    await submit(kb, "a.md", "# A\n\num, versão nova")
    assert (await GetUsage(kb.deps).execute(kb.admin)).usage.documents == 2
    assert await audit(kb, "document.ingest", "denied") == ["denied"]


async def test_bytes_quota(kb: World) -> None:
    await kb.tenants.set_quotas(kb.admin.tenant_id, TenantQuotas(bytes=60))
    await submit(kb, "a.md", "# A\n\n" + "x" * 30)  # 35 bytes
    with pytest.raises(QuotaExceeded):
        await submit(kb, "b.md", "# B\n\n" + "y" * 30)  # 35 more bytes: 70 > 60
    view = await GetUsage(kb.deps).execute(kb.admin)
    assert view.usage.bytes == 35
    assert view.quotas.bytes == 60


async def test_unchanged_resubmit_is_not_charged(kb: World) -> None:
    await submit(kb, "a.md", "# A\n\num")
    await kb.drain_jobs()  # the version becomes "current" only after publication
    await kb.tenants.set_quotas(kb.admin.tenant_id, TenantQuotas(documents=1, bytes=1))
    result = await submit(kb, "a.md", "# A\n\num")  # same content: no new bytes, no new document
    assert result.skipped


async def test_quota_is_per_tenant(kb: World) -> None:
    await kb.tenants.set_quotas(kb.admin.tenant_id, TenantQuotas(documents=0))
    with pytest.raises(QuotaExceeded):
        await submit(kb, "a.md", "# A\n\num")
    other = kb.other_admin
    await CreateKnowledgeBase(kb.deps).execute(other, slug="docs", name="Docs", config=kb_config())
    result = await SubmitIngestion(kb.deps).execute(
        other,
        knowledge_base="docs",
        raw=RawDocument(filename="a.md", mime_type="text/markdown", data=b"# A\n\num"),
    )
    assert not result.skipped
    assert (await GetUsage(kb.deps).execute(other)).quotas == TenantQuotas()


async def test_usage_counts_published_bytes(kb: World) -> None:
    await submit(kb, "a.md", "# A\n\num texto")
    await kb.drain_jobs()
    view = await GetUsage(kb.deps).execute(kb.reader)
    assert view.usage == TenantUsage(documents=1, bytes=len(b"# A\n\num texto"))


async def test_set_quotas_replaces_and_is_audited(kb: World) -> None:
    await kb.tenants.set_quotas(kb.admin.tenant_id, TenantQuotas(documents=5, bytes=100))
    await kb.tenants.set_quotas(kb.admin.tenant_id, TenantQuotas(documents=7))
    assert await kb.tenants.get_quotas(kb.admin.tenant_id) == TenantQuotas(documents=7)
    assert await audit(kb, "tenant.quota_update") == ["success", "success"]
    with pytest.raises(NotFound):
        await kb.tenants.get_quotas(UUID(int=0))


# ---------------------------------------------------------------- api keys


async def test_revoke_api_key(world: World) -> None:
    tenant_id = world.admin.tenant_id
    issued = await world.tenants.issue_api_key(
        tenant_id, principal_name="ci", roles=frozenset({Role.WRITER})
    )
    ctx = await world.tenants.authenticate(issued.key, interface="api")
    assert ctx.tenant_id == tenant_id

    keys = {k.key_prefix: k for k in await world.tenants.list_api_keys(tenant_id)}
    assert keys[issued.key_prefix].principal_name == "ci"
    assert keys[issued.key_prefix].roles == frozenset({Role.WRITER})
    assert not keys[issued.key_prefix].revoked

    await world.tenants.revoke_api_key(tenant_id, issued.key_prefix)
    with pytest.raises(Unauthenticated):
        await world.tenants.authenticate(issued.key, interface="api")
    keys = {k.key_prefix: k for k in await world.tenants.list_api_keys(tenant_id)}
    assert keys[issued.key_prefix].revoked
    assert await audit(world, "api_key.revoke") == ["success"]
    assert await audit(world, "api_key.issue") != []


async def test_cannot_revoke_key_of_another_tenant(world: World) -> None:
    issued = await world.tenants.issue_api_key(
        world.other_admin.tenant_id, principal_name="x", roles=frozenset({Role.READER})
    )
    with pytest.raises(NotFound):
        await world.tenants.revoke_api_key(world.admin.tenant_id, issued.key_prefix)
    ctx = await world.tenants.authenticate(issued.key, interface="api")  # still valid
    assert ctx.tenant_id == world.other_admin.tenant_id
    other_keys = await world.tenants.list_api_keys(world.admin.tenant_id)
    assert issued.key_prefix not in {k.key_prefix for k in other_keys}


# ---------------------------------------------------------------- audit log


async def test_audit_requires_admin(world: World) -> None:
    with pytest.raises(PermissionDenied):
        await ListAuditEvents(world.deps).execute(world.reader)


async def test_audit_events_are_tenant_scoped_and_newest_first(kb: World) -> None:
    await submit(kb, "a.md", "# A\n\num")
    events = await ListAuditEvents(kb.deps).execute(kb.admin, limit=50)
    actions = [e.action for e in events]
    assert "knowledge_base.create" in actions and "document.ingest" in actions
    assert actions.index("document.ingest") < actions.index("knowledge_base.create")
    assert all(e.created_at is not None for e in events)
    assert all(e.tenant_id == kb.admin.tenant_id for e in events)
    other_events = await ListAuditEvents(kb.deps).execute(kb.other_admin, limit=50)
    assert not any(e.action.startswith("document.") for e in other_events)


async def test_audit_filters_and_limit(kb: World) -> None:
    for i in range(3):
        await submit(kb, f"d{i}.md", f"# D{i}\n\ntexto {i}")
    ingests = await ListAuditEvents(kb.deps).execute(kb.admin, action="document.ingest")
    assert len(ingests) == 3
    assert len(await ListAuditEvents(kb.deps).execute(kb.admin, limit=2)) == 2
    assert await ListAuditEvents(kb.deps).execute(kb.admin, outcome="denied") == []
    for bad in (0, 1001):
        with pytest.raises(InvalidArgument):
            await ListAuditEvents(kb.deps).execute(kb.admin, limit=bad)
