"""Reranker for a rerank API in the Cohere format (OpenRouter ``POST /rerank``, ADR-0018).

The request is ``{model, query, documents, top_n}``. The response is
``{results: [{index, relevance_score}]}``, sorted by relevance. The adapter sends the text of
each candidate to the provider.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vlade_rag.core.domain import InvalidArgument, ProviderUnavailable, ScoredChunk
from vlade_rag.integrations.external.http import ProviderHttpClient


class ApiReranker:
    def __init__(self, http: ProviderHttpClient, name: str, model: str) -> None:
        self.http = http
        self.name = name
        self.model = model

    async def rerank(
        self, query: str, candidates: Sequence[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        if not candidates:
            return []
        if top_n < 1:
            raise InvalidArgument("top_n must be 1 or more.")
        n = min(top_n, len(candidates))
        payload: dict[str, Any] = {
            "model": self.model,
            "query": query,
            # A provider rejects an empty document. A chunk is never empty, but be safe.
            "documents": [c.chunk.text or " " for c in candidates],
            "top_n": n,
        }
        data = await self.http.post_json("/rerank", payload)
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            raise ProviderUnavailable(f"{self.name} returned no rerank results.")
        ranked: list[tuple[float, int]] = []
        seen: set[int] = set()
        for item in results:
            index = int(item["index"])
            if not 0 <= index < len(candidates):
                raise ProviderUnavailable(f"{self.name} returned an unknown document index.")
            if index in seen:
                continue
            seen.add(index)
            ranked.append((float(item["relevance_score"]), index))
        # Sort again: the order of the response is not part of the contract. The index is the
        # tie-break, so equal scores keep the order of the candidates.
        ranked.sort(key=lambda pair: (-pair[0], pair[1]))
        return [
            ScoredChunk(candidates[index].chunk, score, rank, "rerank")
            for rank, (score, index) in enumerate(ranked[:n], start=1)
        ]
