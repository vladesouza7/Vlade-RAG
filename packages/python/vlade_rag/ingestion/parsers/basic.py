"""Parsers without third-party dependencies: plain text, Markdown and HTML."""

from __future__ import annotations

from html.parser import HTMLParser

from vlade_rag.core.application.mime import HTML, MARKDOWN, TEXT
from vlade_rag.core.domain import ParsedDocument, RawDocument


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
        if text.startswith("---\n"):  # drop YAML front matter
            end = text.find("\n---", 4)
            if end != -1:
                text = text[end + 4 :]
        return ParsedDocument(text=text, title=_first_heading(text))


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
