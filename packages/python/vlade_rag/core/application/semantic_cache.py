"""Semantic query-result cache over the ``Cache`` port (ADR-0030).

The cache keeps the embedding vector and the result records of recent queries of a knowledge
base. A new query reuses a result when the cosine similarity reaches the configured threshold.
One entry per base epoch, so a publish or a reindex invalidates the cache without a sweep.
The code uses only the standard library; no vector database or numeric dependency is needed.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from vlade_rag.core.domain import TenantContext
from vlade_rag.core.ports import Cache

DEFAULT_THRESHOLD = 0.98
DEFAULT_MAX_ENTRIES = 128
DEFAULT_TTL_SECONDS = 600


@dataclass(frozen=True, slots=True)
class SemanticCacheSettings:
    """Opt-in settings of the semantic cache."""

    enabled: bool = False
    threshold: float = DEFAULT_THRESHOLD
    max_entries: int = DEFAULT_MAX_ENTRIES
    ttl_seconds: int = DEFAULT_TTL_SECONDS


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two vectors of the same space."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return 0.0 if norm_a == 0 or norm_b == 0 else dot / (norm_a * norm_b)


class SemanticCache:
    """Store recent query vectors and reuse results of similar queries."""

    def __init__(self, cache: Cache | None, settings: SemanticCacheSettings) -> None:
        self.cache = cache
        self.settings = settings

    @staticmethod
    def key(kb_id: UUID, epoch: int) -> str:
        return f"semsearch:{kb_id}:{epoch}"

    async def lookup(
        self,
        ctx: TenantContext,
        kb_id: UUID,
        epoch: int,
        vector: Sequence[float],
    ) -> tuple[Mapping[str, Any], ...] | None:
        if self.cache is None or not self.settings.enabled:
            return None
        raw = await self.cache.get(ctx, self.key(kb_id, epoch))
        if raw is None:
            return None
        try:
            entries = json.loads(raw)
        except (ValueError, TypeError):
            return None
        best: tuple[float, tuple[Mapping[str, Any], ...]] = (0.0, ())
        for entry in entries:
            stored = tuple(float(x) for x in entry.get("vector", ()))
            score = cosine(vector, stored)
            if score > best[0]:
                best = (score, tuple(entry.get("results", ())))
        if best[0] < self.settings.threshold or not best[1]:
            return None
        return best[1]

    async def store(
        self,
        ctx: TenantContext,
        kb_id: UUID,
        epoch: int,
        vector: Sequence[float],
        results: Sequence[Mapping[str, Any]],
    ) -> None:
        if self.cache is None or not self.settings.enabled or not results:
            return
        key = self.key(kb_id, epoch)
        raw = await self.cache.get(ctx, key)
        entries: list[dict[str, Any]] = []
        if raw is not None:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, list):
                    entries = loaded
            except (ValueError, TypeError):
                entries = []
        entries.append(
            {
                "vector": [round(float(x), 4) for x in vector],
                "results": list(results),
            }
        )
        entries = entries[-self.settings.max_entries :]
        await self.cache.set(
            ctx,
            key,
            json.dumps(entries, ensure_ascii=False).encode("utf-8"),
            self.settings.ttl_seconds,
        )


__all__ = [
    "DEFAULT_MAX_ENTRIES",
    "DEFAULT_THRESHOLD",
    "DEFAULT_TTL_SECONDS",
    "SemanticCache",
    "SemanticCacheSettings",
    "cosine",
]
