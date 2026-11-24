"""Website connector: crawl HTTPS pages and expose each page as a ``SourceItem``.

The connector reuses the secure downloader in ``download.py``. It never follows a redirect,
stays on the host of a seed and respects the allowed domains and the size limit.
"""

from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator, Sequence
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import RawDocument, SourceItem, TenantContext
from vlade_rag.ingestion.sources.download import host_allowed, read_source

_FILENAME_LIMIT = 120


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.links: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and data.strip():
            self.title.append(data.strip())


def _filename(url: str) -> str:
    parts = urlsplit(url)
    name = parts.path.rstrip("/").rsplit("/", 1)[-1] or "index.html"
    return name[:_FILENAME_LIMIT]


class WebSource:
    """Crawl a small set of pages from HTTPS seeds."""

    name = "web"

    def __init__(
        self,
        deps: Dependencies,
        seeds: Sequence[str],
        *,
        max_pages: int = 50,
        max_depth: int = 2,
    ) -> None:
        if not seeds:
            raise ValueError("The web source needs at least one seed URL.")
        self.deps = deps
        self.seeds = tuple(seeds)
        self.max_pages = max_pages
        self.max_depth = max_depth

    async def list_items(self, ctx: TenantContext, cursor: str | None) -> AsyncIterator[SourceItem]:
        allowed = tuple(self.deps.sources.allowed_domains)
        hosts = {urlsplit(url).hostname for url in self.seeds}
        start = [(cursor, 0)] if cursor else [(url, 0) for url in self.seeds]
        queue: deque[tuple[str, int]] = deque(start)
        visited: set[str] = set()
        emitted = 0
        while queue and emitted < self.max_pages:
            url, depth = queue.popleft()
            parts = urlsplit(url)
            host = parts.hostname
            if (
                url in visited
                or parts.scheme.lower() != "https"
                or host not in hosts
                or not host_allowed(host or "", allowed)
            ):
                continue
            visited.add(url)
            content = await read_source(self.deps, ctx, url)
            if "html" not in (content.mime_type or "").lower():
                continue
            parser = _PageParser()
            parser.feed(content.data.decode("utf-8", errors="replace"))
            title = " ".join(parser.title)
            yield SourceItem(
                uri=url,
                filename=_filename(url),
                mime_type="text/html",
                external_id=url,
                metadata={"url": url, "title": title},
            )
            emitted += 1
            if depth < self.max_depth:
                for href in parser.links:
                    link = urljoin(url, href)
                    target = urlsplit(link)
                    if target.scheme.lower() == "https" and target.hostname in hosts:
                        queue.append((link, depth + 1))

    async def fetch(self, ctx: TenantContext, item: SourceItem) -> RawDocument:
        content = await read_source(self.deps, ctx, item.uri)
        return RawDocument(
            filename=item.filename,
            mime_type=content.mime_type or item.mime_type or "text/html",
            data=content.data,
            source_type="web",
            source_uri=item.uri,
            metadata=dict(item.metadata),
        )


__all__ = ["WebSource"]
