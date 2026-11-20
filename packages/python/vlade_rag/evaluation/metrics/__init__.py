"""Recall@K, Precision@K, MRR and NDCG, computed without an LLM (RF-70).

Every function takes the ranked list of document keys (best first, each key once) and the set of
relevant keys. Relevance is binary. ``k`` is the cutoff of the metric.

- Recall@K: the share of the relevant documents found in the first K positions.
- Precision@K: the share of the first K positions that hold a relevant document.
- MRR (one question): 1 / rank of the first relevant document, 0 if there is none.
- NDCG@K: the gain of each relevant document is 1 / log2(position + 1), divided by the best
  possible gain for the same number of relevant documents.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable, Sequence


def unique_in_order[K: Hashable](items: Iterable[K]) -> list[K]:
    """The items without repetition, each at the position of its first appearance."""
    seen: set[K] = set()
    out: list[K] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _check_k(k: int) -> None:
    if k < 1:
        raise ValueError("k must be 1 or more.")


def recall_at_k[K: Hashable](ranked: Sequence[K], relevant: set[K], k: int) -> float:
    _check_k(k)
    if not relevant:
        return 0.0
    return len(relevant.intersection(ranked[:k])) / len(relevant)


def precision_at_k[K: Hashable](ranked: Sequence[K], relevant: set[K], k: int) -> float:
    _check_k(k)
    return len(relevant.intersection(ranked[:k])) / k


def reciprocal_rank[K: Hashable](ranked: Sequence[K], relevant: set[K]) -> float:
    for position, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / position
    return 0.0


def first_relevant_rank[K: Hashable](ranked: Sequence[K], relevant: set[K]) -> int | None:
    """The 1-based position of the first relevant document, or ``None``."""
    for position, item in enumerate(ranked, start=1):
        if item in relevant:
            return position
    return None


def ndcg_at_k[K: Hashable](ranked: Sequence[K], relevant: set[K], k: int) -> float:
    _check_k(k)
    if not relevant:
        return 0.0
    gain = sum(
        1.0 / math.log2(position + 1)
        for position, item in enumerate(ranked[:k], start=1)
        if item in relevant
    )
    best = sum(1.0 / math.log2(position + 1) for position in range(1, min(len(relevant), k) + 1))
    return gain / best


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
