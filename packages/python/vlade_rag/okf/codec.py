"""Adapter that implements ``WikiPageCodec`` with OKF v0.2 files."""

from __future__ import annotations

from collections.abc import Iterable

from vlade_rag.core.domain import WikiPage
from vlade_rag.okf.parser import parse_page
from vlade_rag.okf.writer import append_log_entry, render_index, render_page


class OkfWikiCodec:
    def parse_page(self, text: str, path: str) -> WikiPage:
        return parse_page(text, path)

    def render_page(self, page: WikiPage) -> str:
        return render_page(page)

    def render_index(self, entries: Iterable[tuple[str, str, str]], title: str) -> str:
        return render_index(entries, title)

    def append_log(self, log: str | None, date: str, item: str, title: str) -> str:
        return append_log_entry(log, date, item, title)
