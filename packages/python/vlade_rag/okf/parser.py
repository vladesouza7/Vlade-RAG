"""Parser and conformance checks for OKF v0.2 bundles.

Only three rules are hard (OKF v0.2 section 11): parseable YAML frontmatter, a non-empty ``type``
on every concept, and the reserved names ``index.md`` and ``log.md``. Every other field is
optional. Unknown fields stay in ``WikiPage.extra`` so a consumer preserves them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vlade_rag.core.domain import InvalidArgument, WikiActor, WikiPage, WikiSource

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the installed extra
    yaml = None


class OkfUnavailable(RuntimeError):
    """Raised when a call needs PyYAML and the ``okf`` extra is not installed."""


def _yaml() -> Any:
    if yaml is None:
        raise OkfUnavailable("Install the 'okf' extra to read or write OKF documents.")
    return yaml


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return the YAML mapping and the markdown body. No frontmatter gives ``({}, text)``."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return {}, text
    end = None
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == "---":
            end = index
            break
    if end is None:
        return {}, text
    header = "".join(lines[1:end])
    body = "".join(lines[end + 1 :]).lstrip("\n")
    data = _yaml().safe_load(header)
    if data is None:
        return {}, body
    if not isinstance(data, dict):
        raise InvalidArgument("OKF frontmatter must be a YAML mapping.")
    return {str(key): value for key, value in data.items()}, body


def _actor(value: Any, field: str) -> WikiActor | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise InvalidArgument(f"OKF '{field}' must be a mapping with 'by'.")
    actor = str(value.get("by") or "")
    if not actor:
        raise InvalidArgument(f"OKF '{field}.by' is required.")
    return WikiActor(by=actor, at=str(value.get("at") or ""))


def _actors(value: Any) -> tuple[WikiActor, ...]:
    if value is None:
        return ()
    items = value if isinstance(value, list) else [value]
    result = []
    for item in items:
        actor = _actor(item, "verified")
        if actor is not None:
            result.append(actor)
    return tuple(result)


def _sources(value: Any) -> tuple[WikiSource, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise InvalidArgument("OKF 'sources' must be a list.")
    result = []
    for item in value:
        if not isinstance(item, dict) or not str(item.get("resource") or ""):
            raise InvalidArgument("Every OKF source needs a non-empty 'resource'.")
        result.append(
            WikiSource(
                resource=str(item["resource"]),
                id=str(item["id"]) if item.get("id") is not None else None,
                title=str(item["title"]) if item.get("title") is not None else None,
                author=str(item["author"]) if item.get("author") is not None else None,
                usage_count=(
                    int(item["usage_count"]) if item.get("usage_count") is not None else None
                ),
                last_modified=(
                    str(item["last_modified"]) if item.get("last_modified") is not None else None
                ),
            )
        )
    return tuple(result)


_KNOWN = frozenset(
    {
        "type",
        "title",
        "description",
        "resource",
        "tags",
        "sources",
        "generated",
        "verified",
        "status",
        "stale_after",
        "body",
    }
)


def parse_page(text: str, path: str) -> WikiPage:
    """Parse one OKF concept. ``path`` is the concept id inside the bundle."""
    frontmatter, body = split_frontmatter(text)
    concept_type = str(frontmatter.get("type") or "").strip()
    if not concept_type:
        raise InvalidArgument(f"OKF concept '{path}' has no non-empty 'type'.")
    status = str(frontmatter.get("status") or "stable")
    if status not in {"draft", "stable", "deprecated"}:
        raise InvalidArgument(f"OKF concept '{path}' has invalid status '{status}'.")
    tags = frontmatter.get("tags")
    if tags is None:
        tags = []
    if not isinstance(tags, list):
        raise InvalidArgument(f"OKF concept '{path}' has a non-list 'tags' field.")
    return WikiPage(
        path=path,
        type=concept_type,
        title=str(frontmatter["title"]) if frontmatter.get("title") is not None else None,
        description=(
            str(frontmatter["description"]) if frontmatter.get("description") is not None else None
        ),
        resource=str(frontmatter["resource"]) if frontmatter.get("resource") is not None else None,
        tags=tuple(str(tag) for tag in tags),
        sources=_sources(frontmatter.get("sources")),
        generated=_actor(frontmatter.get("generated"), "generated"),
        verified=_actors(frontmatter.get("verified")),
        status=status,  # type: ignore[arg-type]
        stale_after=(
            str(frontmatter["stale_after"]) if frontmatter.get("stale_after") is not None else None
        ),
        body=body.lstrip("\n"),
        extra={key: value for key, value in frontmatter.items() if key not in _KNOWN},
    )


def parse_bundle(root: str | Path) -> list[WikiPage]:
    """Parse every concept of an OKF bundle. Reserved names are skipped."""
    directory = Path(root)
    pages = []
    for file in sorted(directory.rglob("*.md")):
        path = file.relative_to(directory).as_posix()
        if Path(path).name in {"index.md", "log.md"}:
            continue
        pages.append(parse_page(file.read_text(encoding="utf-8"), path))
    return pages


def validate_bundle(root: str | Path) -> tuple[str, ...]:
    """Return the conformance problems of a bundle. Empty means conformant."""
    directory = Path(root)
    problems: list[str] = []
    files = sorted(directory.rglob("*.md")) if directory.exists() else []
    for file in files:
        path = file.relative_to(directory).as_posix()
        try:
            frontmatter, _ = split_frontmatter(file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, OkfUnavailable, InvalidArgument) as exc:
            problems.append(f"{path}: {exc}")
            continue
        name = Path(path).name
        if name == "index.md":
            if frontmatter and set(frontmatter) - {"okf_version"}:
                problems.append(f"{path}: index.md accepts only 'okf_version'.")
            continue
        if name == "log.md":
            continue
        if not str(frontmatter.get("type") or "").strip():
            problems.append(f"{path}: missing non-empty 'type'.")
    return tuple(problems)
