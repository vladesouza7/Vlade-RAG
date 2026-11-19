"""PostgreSQL JobQueue, AuditLog and TenantDirectory."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

import asyncpg

from vlade_rag.core.domain import (
    AuditEvent,
    Conflict,
    IngestionJob,
    IngestionStep,
    JobKind,
    JobStatus,
    Metadata,
    NotFound,
    QueryLogEntry,
    Role,
    Tenant,
    TenantContext,
    Unauthenticated,
    uuid7,
)
from vlade_rag.core.domain.api_keys import (
    generate_api_key,
    hash_secret,
    parse_api_key,
    verify_secret,
)
from vlade_rag.core.ports import ClaimedJob, IssuedApiKey
from vlade_rag.knowledge.postgres.db import PostgresDatabase


def _job(row: Mapping[str, Any], steps: tuple[IngestionStep, ...] = ()) -> IngestionJob:
    return IngestionJob(
        id=row["id"],
        tenant_id=row["tenant_id"],
        kind=JobKind(row["kind"]),
        status=JobStatus(row["status"]),
        input=row["input"],
        knowledge_base_id=row["knowledge_base_id"],
        requested_by=row["requested_by"],
        result=row["result"],
        error=row["error"],
        attempt=row["attempt"],
        steps=steps,
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


class PostgresJobQueue:
    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db

    async def enqueue(
        self,
        ctx: TenantContext,
        *,
        kind: JobKind,
        knowledge_base_id: UUID | None,
        input: Metadata,
    ) -> IngestionJob:
        async with self.db.tenant(ctx) as conn:
            row = await conn.fetchrow(
                "INSERT INTO ingestion_jobs (id, tenant_id, knowledge_base_id, kind, status, "
                "requested_by, input) VALUES ($1, $2, $3, $4, 'pending', $5, $6) RETURNING *",
                uuid7(),
                ctx.tenant_id,
                knowledge_base_id,
                kind.value,
                ctx.principal_id,
                dict(input),
            )
        return _job(row)

    async def get(self, ctx: TenantContext, job_id: UUID) -> IngestionJob:
        async with self.db.tenant(ctx) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM ingestion_jobs WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                job_id,
            )
            if row is None:
                raise NotFound("Job does not exist.")
            steps = await conn.fetch(
                "SELECT * FROM ingestion_steps WHERE job_id = $1 ORDER BY started_at, name", job_id
            )
        return _job(
            row,
            tuple(
                IngestionStep(
                    name=s["name"],
                    status=JobStatus(s["status"]),
                    attempt=s["attempt"],
                    document_id=s["document_id"],
                    error=s["error"],
                    started_at=s["started_at"],
                    finished_at=s["finished_at"],
                )
                for s in steps
            ),
        )

    async def claim(self, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        async with self.db.system() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM vlade_claim_job($1, $2)", worker_id, lease_seconds
            )
        if row is None or row["id"] is None:
            return None
        job = _job(row)
        ctx = TenantContext(
            tenant_id=job.tenant_id,
            principal_id=job.requested_by or job.tenant_id,
            roles=frozenset({Role.ADMIN}),
            interface="worker",
        )
        return ClaimedJob(job=job, ctx=ctx)

    async def heartbeat(self, job_id: UUID, worker_id: str, lease_seconds: int) -> None:
        async with self.db.system() as conn:
            await conn.execute(
                "SELECT vlade_heartbeat_job($1, $2, $3)", job_id, worker_id, lease_seconds
            )

    async def record_step(self, ctx: TenantContext, job_id: UUID, step: IngestionStep) -> None:
        async with self.db.tenant(ctx) as conn:
            await conn.execute(
                "INSERT INTO ingestion_steps (id, tenant_id, job_id, document_id, name, status, "
                "attempt, error, started_at, finished_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) "
                "ON CONFLICT (job_id, name) DO UPDATE SET status = EXCLUDED.status, "
                "attempt = EXCLUDED.attempt, error = EXCLUDED.error, "
                "started_at = EXCLUDED.started_at, finished_at = EXCLUDED.finished_at",
                uuid7(),
                ctx.tenant_id,
                job_id,
                step.document_id,
                step.name,
                step.status.value,
                step.attempt,
                None if step.error is None else dict(step.error),
                step.started_at,
                step.finished_at,
            )

    async def complete(self, ctx: TenantContext, job_id: UUID, result: Metadata) -> None:
        async with self.db.tenant(ctx) as conn:
            await conn.execute(
                "UPDATE ingestion_jobs SET status = 'succeeded', result = $3, finished_at = now(), "
                "locked_by = NULL, locked_until = NULL WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                job_id,
                dict(result),
            )

    async def fail(
        self, ctx: TenantContext, job_id: UUID, error: Metadata, *, retry: bool, max_attempts: int
    ) -> None:
        async with self.db.tenant(ctx) as conn:
            await conn.execute(
                "UPDATE ingestion_jobs SET "
                "status = CASE WHEN $4 AND attempt < $5 THEN 'pending' ELSE 'failed' END, "
                "finished_at = CASE WHEN $4 AND attempt < $5 THEN NULL ELSE now() END, "
                "error = $3, locked_by = NULL, locked_until = NULL "
                "WHERE tenant_id = $1 AND id = $2",
                ctx.tenant_id,
                job_id,
                dict(error),
                retry,
                max_attempts,
            )

    async def requeue_expired(self, max_attempts: int) -> int:
        async with self.db.system() as conn:
            return int(await conn.fetchval("SELECT vlade_requeue_expired_jobs($1)", max_attempts))


class PostgresAuditLog:
    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db

    async def record(self, ctx: TenantContext, event: AuditEvent) -> None:
        async with self.db.tenant(ctx) as conn:
            await conn.execute(
                "INSERT INTO audit_events (id, tenant_id, principal_id, interface, action, "
                "resource_type, resource_id, outcome, details, trace_id) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                uuid7(),
                ctx.tenant_id,
                event.principal_id,
                event.interface,
                event.action,
                event.resource_type,
                event.resource_id,
                event.outcome,
                dict(event.details),
                event.trace_id,
            )

    async def record_query(self, ctx: TenantContext, entry: QueryLogEntry) -> None:
        async with self.db.tenant(ctx) as conn:
            await conn.execute(
                "INSERT INTO query_logs (id, tenant_id, knowledge_base_id, principal_id, interface,"
                " mode, query_hash, query_text, result_count, grounded, latency_ms, trace_id) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
                uuid7(),
                ctx.tenant_id,
                entry.knowledge_base_id,
                entry.principal_id,
                entry.interface,
                entry.mode,
                entry.query_hash,
                entry.query_text,
                entry.result_count,
                entry.grounded,
                entry.latency_ms,
                entry.trace_id,
            )


class PostgresTenantDirectory:
    def __init__(self, db: PostgresDatabase, pepper: str) -> None:
        if not pepper:
            raise ValueError("VLADE_SECURITY__API_KEY_PEPPER is required.")
        self.db = db
        self.pepper = pepper

    @staticmethod
    def _ctx(tenant_id: UUID) -> TenantContext:
        return TenantContext(tenant_id, tenant_id, frozenset({Role.ADMIN}), "cli")

    async def create_tenant(self, slug: str, name: str) -> Tenant:
        tenant_id = uuid7()
        try:
            async with self.db.tenant(self._ctx(tenant_id)) as conn:
                await conn.execute(
                    "INSERT INTO tenants (id, slug, name) VALUES ($1, $2, $3)",
                    tenant_id,
                    slug,
                    name,
                )
        except asyncpg.UniqueViolationError:
            raise Conflict(f"Tenant '{slug}' already exists.") from None
        return Tenant(id=tenant_id, slug=slug, name=name)

    async def get_tenant(self, slug: str) -> Tenant:
        async with self.db.system() as conn:
            row = await conn.fetchrow("SELECT * FROM vlade_tenant_by_slug($1)", slug)
        if row is None:
            raise NotFound(f"Tenant '{slug}' does not exist.")
        return Tenant(id=row["id"], slug=row["slug"], name=row["name"], settings=row["settings"])

    async def issue_api_key(
        self, tenant_id: UUID, *, principal_name: str, roles: frozenset[Role]
    ) -> IssuedApiKey:
        key, prefix, secret = generate_api_key()
        principal_id = uuid7()
        async with self.db.tenant(self._ctx(tenant_id)) as conn:
            if not await conn.fetchval("SELECT 1 FROM tenants WHERE id = $1", tenant_id):
                raise NotFound("Tenant does not exist.")
            await conn.execute(
                "INSERT INTO principals (id, tenant_id, name) VALUES ($1, $2, $3)",
                principal_id,
                tenant_id,
                principal_name,
            )
            await conn.execute(
                "INSERT INTO api_keys (id, tenant_id, principal_id, key_prefix, key_hash, roles) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                uuid7(),
                tenant_id,
                principal_id,
                prefix,
                hash_secret(secret, self.pepper),
                sorted(r.value for r in roles),
            )
        return IssuedApiKey(key=key, key_prefix=prefix, principal_id=principal_id, roles=roles)

    async def authenticate(self, api_key: str, *, interface: str) -> TenantContext:
        prefix, secret = parse_api_key(api_key)
        async with self.db.system() as conn:
            row = await conn.fetchrow("SELECT * FROM vlade_authenticate($1)", prefix)
        if row is None or not verify_secret(secret, self.pepper, bytes(row["key_hash"])):
            raise Unauthenticated("Invalid API key.")
        return TenantContext(
            tenant_id=row["tenant_id"],
            principal_id=row["principal_id"],
            roles=frozenset(Role(r) for r in row["roles"]),
            interface=interface,  # type: ignore[arg-type]
        )
