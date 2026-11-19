"""Deterministic, offline embedding provider (feature hashing).

It captures word overlap only, not meaning. Use it for tests, CI and demos without a model.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from collections.abc import Sequence

from vlade_rag import native


def _terms(text: str) -> list[str]:
    out = []
    for start, end in native.token_spans(text):
        token = text[start:end]
        if token[0].isalnum():
            decomposed = unicodedata.normalize("NFD", token.lower())
            out.append("".join(c for c in decomposed if not unicodedata.combining(c)))
    return out


class HashingEmbeddingProvider:
    provider = "hashing"
    max_batch_size = 1024

    def __init__(self, model: str = "hashing-v1", dimension: int = 256) -> None:
        self.model = model
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for term in _terms(text):
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            vector[value % self.dimension] += 1.0 if (value >> 63) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in vector))
        return vector if norm == 0 else [x / norm for x in vector]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
