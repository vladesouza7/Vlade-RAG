"""Fusion strategies (docs/ARCHITECTURE.md section 11.2)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from vlade_rag import native
from vlade_rag.core.domain import ScoredChunk


class RRFFusion:
    """Reciprocal Rank Fusion. Ties go to the better rank in the first retriever list."""

    name = "rrf"

    def __init__(self, k: float = 60.0, weights: Mapping[str, float] | None = None) -> None:
        self.k = k
        self.weights = dict(weights or {})

    def fuse(self, results: Mapping[str, Sequence[ScoredChunk]], top_k: int) -> list[ScoredChunk]:
        names = list(results)
        by_id = {str(item.chunk.id): item for name in names for item in results[name]}
        rankings = [[str(item.chunk.id) for item in results[name]] for name in names]
        weights = [self.weights.get(name, 1.0) for name in names]
        fused = native.rrf_fuse(rankings, self.k, weights, top_k)
        return [
            ScoredChunk(by_id[chunk_id].chunk, score, rank, "fusion")
            for rank, (chunk_id, score) in enumerate(fused, start=1)
        ]


def chunk_ids(results: Sequence[ScoredChunk]) -> list[UUID]:
    return [r.chunk.id for r in results]
