"""Sync a named source connector into a knowledge base (task 5.2, ADR-0029)."""

from __future__ import annotations

from dataclasses import dataclass

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.application.ingestion import SubmitIngestion
from vlade_rag.core.domain import InvalidArgument, TenantContext


@dataclass(frozen=True, slots=True)
class SyncResult:
    ingested: int
    next_cursor: str | None = None


class SyncSource:
    """List the items of a connector and submit each one to the ingestion pipeline.

    The pipeline deduplicates by ``external_id``, so a repeated sync does not create duplicate
    documents. The cursor is passed to the connector; connectors that cannot resume simply
    list the whole source again.
    """

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(
        self,
        ctx: TenantContext,
        *,
        source: str,
        knowledge_base: str,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> SyncResult:
        adapter = self.deps.document_sources.get(source)
        if adapter is None:
            raise InvalidArgument(f"The source '{source}' is not configured on this server.")
        submit = SubmitIngestion(self.deps)
        count = 0
        next_cursor: str | None = None
        async for item in adapter.list_items(ctx, cursor):
            if limit is not None and count >= limit:
                next_cursor = item.uri
                break
            raw = await adapter.fetch(ctx, item)
            result = await submit.execute(
                ctx,
                knowledge_base=knowledge_base,
                raw=raw,
                title=item.filename,
                external_id=item.external_id,
            )
            if not result.skipped:
                count += 1
        return SyncResult(ingested=count, next_cursor=next_cursor)


__all__ = ["SyncResult", "SyncSource"]
