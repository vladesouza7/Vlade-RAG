"""Writers for OKF v0.2 concepts, index files and log files."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from vlade_rag.core.domain import WikiActor, WikiPage, WikiSource
from vlade_rag.okf.parser import _yaml


def _actor(value: WikiActor | None) -> dict[str, str] | None:
    if value is None:
        return None
    result = {"by": value.by}
    if value.at:
        result["at"] = value.at
    return result


def _source(value: WikiSource) -> dict[str, object]:
    result: dict[str, object] = {"resource": value.resource}
    for key in ("id", "title", "author", "usage_count", "last_modified"):
        item = getattr(value, key)
        if item is not None:
            result[key] = item
    return result


def render_page(page: WikiPage) -> str:
    """Render a concept as an OKF v0.2 markdown document."""
    data: dict[str, object] = {"type": page.type}
    for key in ("title", "description", "resource"):
        value = getattr(page, key)
        if value is not None:
            data[key] = value
    if page.tags:
        data["tags"] = list(page.tags)
    if page.sources:
        data["sources"] = [_source(source) for source in page.sources]
    generated = _actor(page.generated)
    if generated is not None:
        data["generated"] = generated
    if page.verified:
        data["verified"] = [_actor(actor) for actor in page.verified]
    if page.status != "stable":
        data["status"] = page.status
    if page.stale_after:
        data["stale_after"] = page.stale_after
    data.update(page.extra)
    header = _yaml().safe_dump(data, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{header}\n---\n\n{page.body.strip()}\n"


def render_index(entries: Iterable[tuple[str, str, str]], title: str = "") -> str:
    """Render an ``index.md``. ``entries`` holds (relative path, label, one-line summary)."""
    parts = [f"# {title}\n\n"] if title else []
    for path, label, summary in entries:
        line = f"* [{label}]({path})"
        if summary:
            line += f" - {summary}"
        parts.append(line + "\n")
    return "".join(parts)


def render_log(title: str, entries: Iterable[tuple[str, str]]) -> str:
    """Render a ``log.md``. ``entries`` holds (ISO date, markdown list item)."""
    parts = [f"# {title}\n\n"]
    for date, item in entries:
        parts.append(f"## {date}\n\n* {item}\n\n")
    return "".join(parts)


def append_log_entry(log: str | None, date: str, item: str, title: str = "Wiki Update Log") -> str:
    """Add one entry at the top of a log, keeping the newest date first."""
    lines = []
    for line in (log or render_log(title, [])).splitlines():
        stripped = line.strip()
        if stripped.startswith("*"):
            lines.append(stripped)
        elif stripped.startswith("## "):
            lines.append("## " + stripped[3:])
    entries: list[tuple[str, str]] = []
    current = ""
    for line in lines:
        if line.startswith("## "):
            current = line[3:]
        elif line.startswith("* ") and current:
            entries.append((current, line[2:]))
        elif line.startswith("* "):
            entries.append((date, line[2:]))
    if entries and entries[0][0] == date:
        first_date, first_item = entries[0]
        entries = [(first_date, first_item), (date, item), *entries[1:]]
    else:
        entries.insert(0, (date, item))
    return render_log(title, entries)


def actor(actor_id: str, at: str = "") -> WikiActor:
    """Build an OKF actor.

    Use ``human:<id>`` for a person and ``<producer>/<version>`` for tools.
    """
    return WikiActor(by=actor_id, at=at)


def extra_of(page: WikiPage) -> Mapping[str, object]:
    """Return the producer-defined frontmatter keys of a page."""
    return page.extra
