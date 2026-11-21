"""Query, generation and answer objects (docs/ARCHITECTURE.md section 4.3)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from vlade_rag.core.domain.errors import UnsupportedFilter
from vlade_rag.core.domain.models import JsonValue

# ---------------------------------------------------------------- metadata filters


@dataclass(frozen=True, slots=True)
class Eq:
    key: str
    value: JsonValue


@dataclass(frozen=True, slots=True)
class In:
    key: str
    values: tuple[JsonValue, ...]


@dataclass(frozen=True, slots=True)
class Exists:
    key: str


@dataclass(frozen=True, slots=True)
class And:
    items: tuple[MetadataFilter, ...]


@dataclass(frozen=True, slots=True)
class Or:
    items: tuple[MetadataFilter, ...]


MetadataFilter = Eq | In | Exists | And | Or


def parse_filter(raw: Mapping[str, JsonValue] | None) -> MetadataFilter | None:
    """Parse the JSON filter format of the API and MCP.

    ``{"k": v}`` is equality. ``{"k": {"in": [...]}}`` is membership. ``{"k": {"exists": true}}``
    tests presence. ``{"$and": [...]}`` and ``{"$or": [...]}`` combine filters. Several keys at the
    top level combine with AND.
    """
    if not raw:
        return None
    items: list[MetadataFilter] = []
    for key, value in raw.items():
        if key in ("$and", "$or"):
            if not isinstance(value, list) or not value:
                raise UnsupportedFilter(f"'{key}' needs a non-empty list.")
            parsed = tuple(f for f in (parse_filter(v) for v in value) if f is not None)
            items.append(And(parsed) if key == "$and" else Or(parsed))
        elif key.startswith("$"):
            raise UnsupportedFilter(f"Unknown operator '{key}'.")
        elif isinstance(value, Mapping):
            if set(value) == {"in"} and isinstance(value["in"], list):
                items.append(In(key, tuple(value["in"])))
            elif set(value) == {"exists"} and value["exists"] is True:
                items.append(Exists(key))
            else:
                raise UnsupportedFilter(f"Unsupported filter for key '{key}'.")
        else:
            items.append(Eq(key, value))
    return items[0] if len(items) == 1 else And(tuple(items))


def matches(flt: MetadataFilter | None, metadata: Mapping[str, JsonValue]) -> bool:
    """Reference evaluation of a filter. Adapters must return the same result."""
    match flt:
        case None:
            return True
        case Eq(key, value):
            return key in metadata and metadata[key] == value
        case In(key, values):
            return key in metadata and metadata[key] in values
        case Exists(key):
            return key in metadata
        case And(items):
            return all(matches(i, metadata) for i in items)
        case Or(items):
            return any(matches(i, metadata) for i in items)
    raise UnsupportedFilter(f"Unknown filter {flt!r}")  # pragma: no cover


# ---------------------------------------------------------------- query and answer


@dataclass(frozen=True, slots=True)
class Query:
    text: str
    knowledge_base_id: UUID
    filters: MetadataFilter | None = None
    language: str | None = None
    # Names of the retrievers that run this query. None: every retriever of the base. A query
    # transformer sets it, for example HyDE sends its hypothetical answer only to "dense".
    retrievers: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class Citation:
    index: int
    document_id: UUID
    chunk_id: UUID
    document_title: str
    page: int | None
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    citations: tuple[Citation, ...]
    grounded: bool
    prompt_name: str
    prompt_version: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    trace_id: str | None = None


# ---------------------------------------------------------------- LLM messages


Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class GenerationParams:
    model: str
    temperature: float = 0.1
    max_output_tokens: int = 1024
    stop: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class Generation:
    text: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class GenerationDelta:
    text: str
    usage: TokenUsage | None = None  # present in the last delta when the provider reports it
