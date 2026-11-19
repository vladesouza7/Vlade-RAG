"""Translate ``MetadataFilter`` into SQL over ``chunks.metadata`` (JSONB).

Values are bound parameters. JSONB values are passed as Python objects: the connection codec
encodes them (passing a JSON string would store a JSON string, not an object).
"""

from __future__ import annotations

from typing import Any

from vlade_rag.core.domain import MetadataFilter, UnsupportedFilter
from vlade_rag.core.domain.query import And, Eq, Exists, In, Or


class SqlParams:
    def __init__(self, start: int) -> None:
        self.values: list[Any] = []
        self.start = start

    def add(self, value: Any) -> str:
        self.values.append(value)
        return f"${self.start + len(self.values) - 1}"


def filter_sql(flt: MetadataFilter | None, params: SqlParams, column: str = "c.metadata") -> str:
    match flt:
        case None:
            return "TRUE"
        case Eq(key, value):
            return f"{column} @> {params.add({key: value})}::jsonb"
        case In(key, values):
            if not values:
                return "FALSE"
            parts = [f"{column} @> {params.add({key: v})}::jsonb" for v in values]
            return "(" + " OR ".join(parts) + ")"
        case Exists(key):
            return f"{column} ? {params.add(key)}"
        case And(items):
            return "(" + " AND ".join(filter_sql(i, params, column) for i in items) + ")"
        case Or(items):
            return "(" + " OR ".join(filter_sql(i, params, column) for i in items) + ")"
    raise UnsupportedFilter(f"Unsupported filter {flt!r}")  # pragma: no cover
