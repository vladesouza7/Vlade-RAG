"""LLM-Wiki use cases: OKF pages written by a model, read, linted and maintained (task 6.12).

The raw sources stay immutable in a knowledge base. The wiki is a second, persistent artifact:
each page is an OKF v0.2 markdown document, with provenance, trust and lifecycle in frontmatter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.application.search import Search
from vlade_rag.core.domain import (
    GenerationParams,
    InvalidArgument,
    Message,
    NotFound,
    Role,
    ScoredChunk,
    TenantContext,
    WikiActor,
    WikiPage,
    WikiSource,
)
from vlade_rag.core.ports import WikiPageCodec, WikiStore

_RESERVED = frozenset({"index.md", "log.md"})
_LINK = re.compile(r"\]\(([^)]+\.md)\)")
_CITATION = re.compile(r"\[(\d{1,3})\]")


@dataclass(frozen=True, slots=True)
class WikiPageView:
    path: str
    page: WikiPage
    content: str


@dataclass(frozen=True, slots=True)
class WikiLintReport:
    pages: int
    links: int
    problems: tuple[str, ...]
    orphans: tuple[str, ...]


def _store(deps: Dependencies) -> WikiStore:
    if deps.wiki_store is None:
        raise NotFound("This server has no wiki store configured.")
    return deps.wiki_store


def _codec(deps: Dependencies) -> WikiPageCodec:
    if deps.wiki_codec is None:
        raise NotFound("This server has no OKF codec configured.")
    return deps.wiki_codec


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "concept")[:80]


def _source_of(chunk: ScoredChunk, number: int, slug: str) -> WikiSource:
    return WikiSource(
        id=str(number),
        resource=f"vlade://kb/{slug}/documents/{chunk.chunk.document_id}#chunk/{chunk.chunk.id}",
        title=chunk.chunk.document_title,
    )


def _format_sources(results: list[ScoredChunk], kb_slug: str) -> tuple[str, tuple[WikiSource, ...]]:
    parts = []
    for number, item in enumerate(results, start=1):
        chunk = item.chunk
        page = f' page="{chunk.page}"' if chunk.page is not None else ""
        parts.append(
            f'<source id="{number}" document="{chunk.document_title}"{page}>\n'
            f"{chunk.text}\n</source>"
        )
    sources = tuple(_source_of(item, i, kb_slug) for i, item in enumerate(results, 1))
    return "\n\n".join(parts), sources


async def _update_index(
    store: WikiStore, deps: Dependencies, ctx: TenantContext, knowledge_base: str
) -> None:
    paths = [path for path in await store.list(ctx, knowledge_base) if path not in _RESERVED]
    entries = []
    for path in paths:
        content = await store.get(ctx, knowledge_base, path)
        if content is None:
            continue
        try:
            page = _codec(deps).parse_page(content, path)
        except InvalidArgument:
            continue
        entries.append((path, page.title or Path(path).stem, page.description or ""))
    await store.put(
        ctx, knowledge_base, "index.md", _codec(deps).render_index(entries, knowledge_base)
    )


class ListWikiPages:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, ctx: TenantContext, knowledge_base: str) -> tuple[WikiPageView, ...]:
        ctx.require(Role.READER)
        pages = []
        for path in await _store(self.deps).list(ctx, knowledge_base):
            if path in _RESERVED:
                continue
            content = await _store(self.deps).get(ctx, knowledge_base, path)
            if content is None:
                continue
            pages.append(WikiPageView(path, _codec(self.deps).parse_page(content, path), content))
        return tuple(pages)


class GetWikiPage:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, ctx: TenantContext, knowledge_base: str, path: str) -> WikiPageView:
        ctx.require(Role.READER)
        if path in _RESERVED:
            raise NotFound(f"Wiki page '{path}' does not exist.")
        content = await _store(self.deps).get(ctx, knowledge_base, path)
        if content is None:
            raise NotFound(f"Wiki page '{path}' does not exist.")
        return WikiPageView(path, _codec(self.deps).parse_page(content, path), content)


class WriteWikiPage:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, ctx: TenantContext, knowledge_base: str, page: WikiPage) -> WikiPage:
        ctx.require(Role.WRITER)
        if not page.path.endswith(".md") or Path(page.path).name in _RESERVED:
            raise InvalidArgument("A wiki page needs a .md path that is not reserved.")
        codec = _codec(self.deps)
        content = codec.render_page(page)
        codec.parse_page(content, page.path)  # conformance check before writing
        store = _store(self.deps)
        existed = await store.get(ctx, knowledge_base, page.path) is not None
        await store.put(ctx, knowledge_base, page.path, content)
        await _update_index(store, self.deps, ctx, knowledge_base)
        date = datetime.now(UTC).date().isoformat()
        action = "Update" if existed else "Creation"
        label = page.title or Path(page.path).stem
        log = await store.get(ctx, knowledge_base, "log.md")
        await store.put(
            ctx,
            knowledge_base,
            "log.md",
            codec.append_log(
                log, date, f"**{action}**: [{label}]({page.path}).", "Wiki Update Log"
            ),
        )
        return page


class DeleteWikiPage:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, ctx: TenantContext, knowledge_base: str, path: str) -> None:
        ctx.require(Role.ADMIN)
        store = _store(self.deps)
        if await store.get(ctx, knowledge_base, path) is None:
            raise NotFound(f"Wiki page '{path}' does not exist.")
        await store.delete(ctx, knowledge_base, path)
        await _update_index(store, self.deps, ctx, knowledge_base)


class LintWiki:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(self, ctx: TenantContext, knowledge_base: str) -> WikiLintReport:
        ctx.require(Role.READER)
        pages = await ListWikiPages(self.deps).execute(ctx, knowledge_base)
        problems: list[str] = []
        targets: set[str] = set()
        inbound: set[str] = set()
        now = datetime.now(UTC)
        for view in pages:
            page = view.page
            for match in _LINK.finditer(page.body):
                target = match.group(1).lstrip("/")
                targets.add(target)
                if target in {item.path for item in pages}:
                    inbound.add(target)
            if page.stale_after:
                try:
                    when = datetime.fromisoformat(page.stale_after.replace("Z", "+00:00"))
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=UTC)
                    if now >= when:
                        problems.append(f"{page.path}: stale after {page.stale_after}.")
                except ValueError:
                    problems.append(f"{page.path}: invalid 'stale_after'.")
        paths = {view.path for view in pages}
        for target in sorted(targets - paths):
            problems.append(f"Broken link: {target}.")
        orphans = tuple(sorted(paths - inbound - {"index.md", "log.md"})) if paths else ()
        for path in orphans:
            problems.append(f"Orphan page: {path}.")
        for name in ("index.md", "log.md"):
            if await _store(self.deps).get(ctx, knowledge_base, name) is None:
                problems.append(f"Missing {name}.")
        return WikiLintReport(len(pages), len(targets), tuple(problems), orphans)


class SynthesizeWikiPage:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(
        self,
        ctx: TenantContext,
        knowledge_base: str,
        subject: str,
        path: str | None = None,
        top_k: int = 8,
    ) -> WikiPageView:
        ctx.require(Role.WRITER)
        kb = await self.deps.repository.get_knowledge_base(ctx, knowledge_base)
        search = await Search(self.deps).execute(
            ctx, knowledge_base=knowledge_base, text=subject, top_k=top_k
        )
        results = search.results
        if not results:
            raise InvalidArgument("No source chunks were found for this subject.")
        scored = [item for item in results if isinstance(item, ScoredChunk)]
        sources_text, sources = _format_sources(scored, knowledge_base)
        template = await self.deps.prompts.get("wiki_synthesis", kb.language)
        llm = self.deps.llms(kb.config.generation)
        generation = await llm.generate(
            [
                Message(role="system", content=template.system),
                Message(
                    role="user",
                    content=template.render_user(sources=sources_text, subject=subject),
                ),
            ],
            GenerationParams(
                model=kb.config.generation.model,
                temperature=kb.config.generation.temperature,
                max_output_tokens=kb.config.generation.max_output_tokens,
            ),
        )
        body = _CITATION.sub(lambda match: f"[^{match.group(1)}]", generation.text.strip())
        footnotes = "\n".join(
            f"[^{source.id}]: {source.title or source.resource}" for source in sources
        )
        page = WikiPage(
            path=path or f"{_slug(subject)}.md",
            type="Topic",
            title=subject,
            sources=sources,
            generated=WikiActor(by="vlade-rag/wiki-synthesis"),
            body=f"{body}\n\n{footnotes}\n",
        )
        await WriteWikiPage(self.deps).execute(ctx, knowledge_base, page)
        content = await _store(self.deps).get(ctx, knowledge_base, page.path)
        return WikiPageView(page.path, page, content or "")
