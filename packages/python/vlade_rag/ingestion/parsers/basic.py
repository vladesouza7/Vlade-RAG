"""Parsers without third-party dependencies: plain text, Markdown and HTML."""

from __future__ import annotations

from html.parser import HTMLParser

from vlade_rag.core.application.mime import HTML, MARKDOWN, TEXT
from vlade_rag.core.domain import Metadata, ParsedDocument, RawDocument
from vlade_rag.okf.parser import OkfUnavailable, split_frontmatter


def _json_value(value: object) -> object:
    """Keep metadata JSON-compatible for filters and storage."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _okf_metadata(text: str) -> tuple[Metadata, str]:
    """Split OKF frontmatter from the text. Without the extra, keep the old behavior."""
    try:
        frontmatter, body = split_frontmatter(text)
    except OkfUnavailable:
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            return {}, text[end + 4 :] if end != -1 else text
        return {}, text
    return {f"okf_{key}": _json_value(value) for key, value in frontmatter.items()}, body


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
    return None


class TextParser:
    mime_types = frozenset({TEXT})

    async def parse(self, raw: RawDocument) -> ParsedDocument:
        return ParsedDocument(text=raw.data.decode("utf-8"))


class MarkdownParser:
    mime_types = frozenset({MARKDOWN})

    async def parse(self, raw: RawDocument) -> ParsedDocument:
        text = raw.data.decode("utf-8")
        metadata, body = _okf_metadata(text)
        title = str(metadata["okf_title"]) if metadata.get("okf_title") else _first_heading(body)
        return ParsedDocument(text=body, title=title, metadata=metadata)


_BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "tr", "table", "pre"}
_SKIP = {"script", "style", "noscript", "template", "svg", "head"}


class _HtmlToMarkdown(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self.skip_depth += 1
        if tag == "title":
            self._in_title = True
        elif len(tag) == 2 and tag[0] == "h" and tag[1].isdigit():
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in ("br",):
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")
        elif tag in _BLOCK:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self._in_title = False
        elif (len(tag) == 2 and tag[0] == "h" and tag[1].isdigit()) or tag in _BLOCK:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title = (self.title or "") + data.strip()
            return
        if self.skip_depth:
            return
        self.parts.append(" ".join(data.split()) if data.strip() else " ")


class HtmlParser:
    mime_types = frozenset({HTML})

    async def parse(self, raw: RawDocument) -> ParsedDocument:
        converter = _HtmlToMarkdown()
        converter.feed(raw.data.decode("utf-8"))
        converter.close()
        text = "".join(converter.parts)
        return ParsedDocument(text=text, title=converter.title or _first_heading(text))


def basic_parsers() -> list[TextParser | MarkdownParser | HtmlParser]:
    return [TextParser(), MarkdownParser(), HtmlParser()]
