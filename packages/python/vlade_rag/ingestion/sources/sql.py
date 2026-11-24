"""SQL database connector: turn the rows of a read-only query into documents.

The adapter needs the ``sql`` extra. Operators should also give the query role read-only
permissions in the database. This adapter is separate from the internal PostgreSQL adapters
(ADR-0016); it reads an external database chosen by configuration.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

from pydantic import SecretStr

from vlade_rag.core.domain import InvalidArgument, RawDocument, SourceItem, TenantContext

_READ_PREFIXES = ("select", "with", "values")


def _json_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class SqlSource:
    """Read rows of one configured query and expose each row as a document."""

    name = "sql"

    def __init__(
        self,
        url: SecretStr | None,
        query: str | None,
        *,
        filename_columns: Sequence[str] = (),
        max_rows: int = 1000,
    ) -> None:
        if url is None or not url.get_secret_value():
            raise InvalidArgument("The SQL source needs VLADE_SOURCES__SQL__URL.")
        if not query or not _read_only(query):
            raise InvalidArgument("The SQL source query must be a single read-only SELECT.")
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
        except ImportError as exc:
            raise InvalidArgument(
                'The sql source needs the "sql" extra: pip install "vlade-rag[sql]"'
            ) from exc
        self._engine = create_async_engine(url.get_secret_value())
        self.query = query
        self.filename_columns = tuple(filename_columns)
        self.max_rows = max_rows

    async def close(self) -> None:
        await self._engine.dispose()

    async def list_items(self, ctx: TenantContext, cursor: str | None) -> AsyncIterator[SourceItem]:
        from sqlalchemy import text

        offset = int(cursor or 0)
        async with self._engine.connect() as conn:
            result = await conn.execute(text(self.query))
            columns = list(result.keys())
            rows = result.fetchmany(self.max_rows)
        for position, row in enumerate(rows, start=offset):
            values = {
                column: _json_value(value) for column, value in zip(columns, row, strict=True)
            }
            fingerprint = hashlib.sha256(
                json.dumps(values, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            name = "-".join(
                str(values[column]) for column in self.filename_columns if column in values
            )
            yield SourceItem(
                uri=f"sql://row/{fingerprint[:16]}",
                filename=(name or f"row-{position}")[:120] + ".json",
                mime_type="application/json",
                external_id=fingerprint,
                metadata={"row": values, "offset": position},
            )

    async def fetch(self, ctx: TenantContext, item: SourceItem) -> RawDocument:
        payload = json.dumps(item.metadata, ensure_ascii=False, default=str).encode("utf-8")
        return RawDocument(
            filename=item.filename,
            mime_type="application/json",
            data=payload,
            source_type="sql",
            source_uri=item.uri,
            metadata=dict(item.metadata),
        )


def _read_only(query: str) -> bool:
    """Accept a single SELECT/WITH/VALUES statement, without embedded semicolons."""
    raw = query.strip().rstrip(";").strip()
    return bool(raw) and ";" not in raw and raw.lower().startswith(_READ_PREFIXES)


__all__ = ["SqlSource"]
