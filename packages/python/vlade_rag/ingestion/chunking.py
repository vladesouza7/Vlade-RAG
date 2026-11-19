"""TextNormalizer and Chunker adapters backed by ``vlade_rag.native``."""

from __future__ import annotations

from vlade_rag import native
from vlade_rag.core.domain import ChunkDraft, ParsedDocument
from vlade_rag.core.ports import ChunkingParams


class NativeTextNormalizer:
    def __init__(self, dehyphenate: bool = True) -> None:
        self.dehyphenate = dehyphenate

    def normalize(self, text: str) -> str:
        return native.normalize_text(text, self.dehyphenate)


class NativeChunker:
    name = "native"

    def split(self, document: ParsedDocument, params: ChunkingParams) -> list[ChunkDraft]:
        spans = native.split_text(
            document.text, params.strategy, params.max_tokens, params.overlap_tokens
        )
        return [
            ChunkDraft(
                ordinal=i,
                text=document.text[start:end],
                token_count=tokens,
                start_offset=start,
                end_offset=end,
                page=document.page_at(start),
                section=document.section_at(start),
            )
            for i, (start, end, tokens) in enumerate(spans)
        ]
