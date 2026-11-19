"""PDF and DOCX parser with Docling (ADR-0010). Install with the ``docling`` extra.

Docling exports each page as Markdown, so the parser keeps page offsets and headings.
The conversion is CPU-bound and runs in a worker thread.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any

from vlade_rag.core.application.mime import DOCX, PDF
from vlade_rag.core.domain import InvalidArgument, ParsedDocument, RawDocument


class DoclingParser:
    mime_types = frozenset({PDF, DOCX})

    def __init__(self, converter: Any | None = None) -> None:
        self._converter = converter

    @property
    def converter(self) -> Any:
        if self._converter is None:  # model loading is slow: create on first use
            from docling.document_converter import DocumentConverter

            self._converter = DocumentConverter()
        return self._converter

    def _convert(self, raw: RawDocument) -> ParsedDocument:
        try:
            result = self.converter.convert(_stream(raw.filename, raw.data))
        except Exception as exc:  # Docling raises several exception types for bad input
            raise InvalidArgument(f"Docling could not read '{raw.filename}': {exc}") from exc
        document = result.document
        page_numbers = sorted(getattr(document, "pages", {}) or {})
        if len(page_numbers) <= 1:
            return ParsedDocument(text=document.export_to_markdown(), title=_title(document))
        parts: list[str] = []
        starts: list[int] = []
        offset = 0
        for number in page_numbers:
            page_text = document.export_to_markdown(page_no=number)
            starts.append(offset)
            parts.append(page_text)
            offset += len(page_text) + 2
        return ParsedDocument(
            text="\n\n".join(parts), title=_title(document), page_starts=tuple(starts)
        )

    async def parse(self, raw: RawDocument) -> ParsedDocument:
        return await asyncio.to_thread(self._convert, raw)


def _stream(name: str, data: bytes) -> Any:
    try:
        from docling.datamodel.base_models import DocumentStream
    except ImportError:  # a test converter accepts any object with name and stream
        from types import SimpleNamespace

        return SimpleNamespace(name=name, stream=BytesIO(data))
    return DocumentStream(name=name, stream=BytesIO(data))


def _title(document: Any) -> str | None:
    name = getattr(document, "name", None)
    return str(name) if name else None
