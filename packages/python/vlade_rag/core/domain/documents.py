"""Input documents before chunking."""

from __future__ import annotations

from dataclasses import dataclass, field

from vlade_rag.core.domain.models import Metadata


@dataclass(frozen=True, slots=True)
class SourceItem:
    """A document a DocumentSource can fetch."""

    uri: str
    filename: str
    mime_type: str | None = None
    external_id: str | None = None
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawDocument:
    filename: str
    mime_type: str
    data: bytes
    source_type: str = "upload"
    source_uri: str | None = None
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Section:
    """A heading range in the extracted text."""

    title: str
    start_offset: int
    end_offset: int
    level: int = 1


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Text extracted from a RawDocument.

    ``page_starts[i]`` is the offset where page ``i + 1`` begins. Empty when the format has no
    pages. ``sections`` lists headings in order.
    """

    text: str
    title: str | None = None
    page_starts: tuple[int, ...] = ()
    sections: tuple[Section, ...] = ()
    metadata: Metadata = field(default_factory=dict)

    def page_at(self, offset: int) -> int | None:
        if not self.page_starts:
            return None
        page = None
        for index, start in enumerate(self.page_starts):
            if start > offset:
                break
            page = index + 1
        return page

    def section_at(self, offset: int) -> str | None:
        current = None
        for section in self.sections:
            if section.start_offset > offset:
                break
            current = section.title
        return current
