"""Maintenance tasks of the operations module (roadmap 4.4).

Cleanup is conservative: an active space is never deleted, a building space is kept while a
reindex job is active for the tenant, and every space has a grace period. The same period applies
to superseded versions (ARCHITECTURE section 10.2).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from vlade_rag.core.application import Dependencies
from vlade_rag.core.domain import JobKind, SpaceStatus
from vlade_rag.core.ports import SpaceMaintenanceInfo

DEFAULT_GRACE = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class CleanupReport:
    """Spaces and versions selected for deletion (or deleted when not in dry-run mode)."""

    retired_spaces: int
    building_spaces: int
    versions: int


@dataclass(frozen=True, slots=True)
class HealthReport:
    ok: bool
    failures: tuple[str, ...]


class OpsService:
    """Cleanup, job recovery and health checks over the runtime dependencies."""

    def __init__(
        self,
        deps: Dependencies,
        *,
        checks: Mapping[str, Callable[[], Awaitable[Any]]] | None = None,
    ) -> None:
        self.deps = deps
        self.checks = dict(checks or {})

    async def cleanup(
        self,
        ctx: Any,
        *,
        retired_after: timedelta = DEFAULT_GRACE,
        building_after: timedelta = DEFAULT_GRACE,
        dry_run: bool = False,
    ) -> CleanupReport:
        """Delete retired spaces, orphan building spaces and old superseded versions."""
        repo = self.deps.repository
        now = datetime.now(UTC)
        bases = await repo.list_knowledge_bases(ctx)
        active_spaces = {kb.active_embedding_space_id for kb in bases}

        async def reindex_busy() -> bool:
            for base in bases:
                active = await self.deps.job_queue.find_active(ctx, base.id, JobKind.REINDEX)
                if active is not None:
                    return True
            return False

        retired = building = 0
        for info in await repo.list_spaces_for_maintenance(ctx):
            if await self._delete_space(
                ctx,
                info,
                now=now,
                grace=retired_after,
                active_spaces=active_spaces,
                reindex_busy=reindex_busy,
                dry_run=dry_run,
            ):
                if info.space.status is SpaceStatus.RETIRED:
                    retired += 1
                else:
                    building += 1
        cutoff = now - max(retired_after, building_after)
        if dry_run:
            versions = await repo.count_superseded_versions(ctx, cutoff)
        else:
            versions = await repo.delete_superseded_versions(ctx, cutoff)
        return CleanupReport(retired, building, versions)

    async def _delete_space(
        self,
        ctx: Any,
        info: SpaceMaintenanceInfo,
        *,
        now: datetime,
        grace: timedelta,
        active_spaces: set[Any],
        reindex_busy: Callable[[], Awaitable[bool]],
        dry_run: bool,
    ) -> bool:
        status = info.space.status
        if status not in (SpaceStatus.RETIRED, SpaceStatus.BUILDING):
            return False
        if info.space.id in active_spaces:
            return False
        if status is SpaceStatus.BUILDING and await reindex_busy():
            # A reindex may still be filling this space, even when the lease expired.
            return False
        moment = info.retired_at or info.created_at
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        if now - moment < grace:
            return False
        if dry_run:
            return True
        try:
            # Drop the physical index first: the definer function checks that the space
            # belongs to the tenant, and a failure must not leave an orphan index.
            await self.deps.vector_index.drop_space(ctx, info.space)
        except Exception:
            return False
        return await self.deps.repository.delete_embedding_space(ctx, info.space.id)

    async def recover_jobs(self) -> int:
        """Return expired jobs of crashed workers to the queue (ARCHITECTURE section 10.1)."""
        return await self.deps.job_queue.requeue_expired(self.deps.limits.job_max_attempts)

    async def health(self) -> HealthReport:
        """Run the readiness probes without raising. Used by ``vlade-rag ops health``."""
        failures = []
        for name, probe in self.checks.items():
            try:
                await probe()
            except Exception:
                failures.append(name)
        return HealthReport(ok=not failures, failures=tuple(failures))
