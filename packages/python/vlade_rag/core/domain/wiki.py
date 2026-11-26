"""Wiki pages and the OKF v0.2 frontmatter families (phase 6, tasks 6.10 and 6.12).

The domain does not read or write files. ``vlade_rag.okf`` converts these objects to and from
OKF markdown documents. The names follow the Open Knowledge Format v0.2 specification:
https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

WikiStatus = Literal["draft", "stable", "deprecated"]

RESERVED_FILENAMES = frozenset({"index.md", "log.md"})


@dataclass(frozen=True, slots=True)
class WikiActor:
    """A producer or a verification event. ``by`` follows the OKF actor convention."""

    by: str
    at: str = ""


@dataclass(frozen=True, slots=True)
class WikiSource:
    """A source a concept derives from. ``resource`` is required by OKF v0.2."""

    resource: str
    id: str | None = None
    title: str | None = None
    author: str | None = None
    usage_count: int | None = None
    last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class WikiPage:
    """One OKF concept. The file path inside the bundle is the concept id."""

    path: str
    type: str
    title: str | None = None
    description: str | None = None
    resource: str | None = None
    tags: tuple[str, ...] = ()
    sources: tuple[WikiSource, ...] = ()
    generated: WikiActor | None = None
    verified: tuple[WikiActor, ...] = ()
    status: WikiStatus = "stable"
    stale_after: str | None = None
    body: str = ""
    extra: dict[str, object] = field(default_factory=dict)
