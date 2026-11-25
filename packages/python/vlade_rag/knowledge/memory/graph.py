"""In-memory ``GraphIndex`` for tests and prototypes (phase 6).

It does not call an LLM. Capitalized names become entities, and consecutive entities of a chunk
become relations. Search matches the query words against entity names and returns the chunks of
the matched entities. It only exercises the contract; it does not measure graph quality.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from uuid import UUID

from vlade_rag.core.domain import Chunk, ChunkHit, KnowledgeBase, TenantContext
from vlade_rag.core.ports import GraphEntity, GraphRelation, GraphSearchResult

_NAME = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]+(?:\s(?:d[aeo]s?\s)?[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]+)*")
_STOP = frozenset({"O", "A", "Os", "As", "Em", "No", "Na", "Para", "Segundo", "The", "In", "It"})


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", _fold(text)) if len(w) > 2}


@dataclass
class _Workspace:
    documents: dict[UUID, UUID] = field(default_factory=dict)  # document -> version
    chunks: dict[UUID, tuple[UUID, list[str]]] = field(default_factory=dict)  # chunk -> doc, names


class MemoryGraphIndex:
    name = "memory-graph"

    def __init__(self) -> None:
        self._spaces: dict[tuple[UUID, UUID], _Workspace] = {}

    def _space(self, ctx: TenantContext, kb: KnowledgeBase) -> _Workspace:
        # The partition comes from the caller context and the base, never from user input.
        return self._spaces.setdefault((ctx.tenant_id, kb.id), _Workspace())

    @staticmethod
    def _names(text: str) -> list[str]:
        names: list[str] = []
        for match in _NAME.finditer(text):
            name = match.group(0).strip()
            if name not in _STOP and len(name) > 2 and name not in names:
                names.append(name)
        return names

    async def index_document(
        self,
        ctx: TenantContext,
        kb: KnowledgeBase,
        document_id: UUID,
        version_id: UUID,
        chunks: Sequence[Chunk],
    ) -> int:
        space = self._space(ctx, kb)
        await self.delete_document(ctx, kb, document_id)
        space.documents[document_id] = version_id
        for chunk in chunks:
            space.chunks[chunk.id] = (document_id, self._names(chunk.text))
        return len(chunks)

    async def delete_document(
        self, ctx: TenantContext, kb: KnowledgeBase, document_id: UUID
    ) -> int:
        space = self._space(ctx, kb)
        if document_id not in space.documents:
            return 0
        del space.documents[document_id]
        for chunk_id in [c for c, (doc, _) in space.chunks.items() if doc == document_id]:
            del space.chunks[chunk_id]
        return 1

    async def search(
        self, ctx: TenantContext, kb: KnowledgeBase, text: str, *, mode: str, top_k: int
    ) -> GraphSearchResult:
        space = self._space(ctx, kb)
        terms = _words(text)
        scores: dict[UUID, float] = {}
        entities: dict[str, GraphEntity] = {}
        relations: dict[tuple[str, str], GraphRelation] = {}
        for chunk_id, (_, names) in space.chunks.items():
            matched = [n for n in names if _words(n) & terms]
            if not matched:
                continue
            scores[chunk_id] = float(len(matched))
            for name in matched:
                entities.setdefault(
                    name, GraphEntity(name, "concept", f"{name} appears in the text.")
                )
            for a, b in pairwise(names):
                if a in matched or b in matched:
                    relations.setdefault(
                        (a, b), GraphRelation(a, b, "related", f"{a} is related to {b}.")
                    )
        ranked = sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))
        return GraphSearchResult(
            entities=tuple(entities.values())[:top_k],
            relations=tuple(relations.values())[:top_k],
            chunk_hits=tuple(ChunkHit(cid, score) for cid, score in ranked[:top_k]),
        )
