"""Adapter factories and plugin registry (ADR-0002, docs/ARCHITECTURE.md section 9.3).

The registry maps ``(kind, name)`` to a factory. Built-in adapters register in
``vlade_rag.bootstrap``. External packages register through the entry point group
``vlade_rag.plugins``: each entry point resolves to a ``PluginSpec`` or a list of them.
This module imports no adapter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any, Literal

from vlade_rag.core.domain import InvalidArgument

PluginKind = Literal[
    "source",
    "parser",
    "chunker",
    "embeddings",
    "vector_index",
    "lexical_index",
    "reranker",
    "query_transformer",
    "llm",
    "prompt_registry",
    "object_storage",
    "cache",
    "evaluator",
]
ENTRY_POINT_GROUP = "vlade_rag.plugins"


@dataclass(frozen=True, slots=True)
class PluginSpec:
    kind: PluginKind
    name: str
    factory: Callable[..., Any]
    description: str = ""


class DuplicatePluginError(RuntimeError):
    pass


class Registry:
    def __init__(self) -> None:
        self._specs: dict[tuple[str, str], PluginSpec] = {}

    def register(self, spec: PluginSpec) -> None:
        key = (spec.kind, spec.name)
        if key in self._specs:
            raise DuplicatePluginError(
                f"Plugin '{spec.name}' of kind '{spec.kind}' already exists."
            )
        self._specs[key] = spec

    def register_all(self, specs: Iterable[PluginSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def get(self, kind: PluginKind, name: str) -> PluginSpec:
        try:
            return self._specs[(kind, name)]
        except KeyError:
            known = ", ".join(sorted(n for k, n in self._specs if k == kind)) or "none"
            raise InvalidArgument(f"Unknown {kind} adapter '{name}'. Available: {known}.") from None

    def create(self, kind: PluginKind, name: str, *args: Any, **kwargs: Any) -> Any:
        return self.get(kind, name).factory(*args, **kwargs)

    def names(self, kind: PluginKind) -> list[str]:
        return sorted(n for k, n in self._specs if k == kind)

    def load_entry_points(self, group: str = ENTRY_POINT_GROUP) -> int:
        """Register every plugin published under ``group``. Returns the number registered."""
        count = 0
        for ep in entry_points(group=group):
            loaded = ep.load()
            specs = loaded if isinstance(loaded, list | tuple) else [loaded]
            for spec in specs:
                if not isinstance(spec, PluginSpec):
                    raise TypeError(f"Entry point '{ep.name}' does not resolve to a PluginSpec.")
                self.register(spec)
                count += 1
        return count


__all__ = [
    "ENTRY_POINT_GROUP",
    "DuplicatePluginError",
    "PluginKind",
    "PluginSpec",
    "Registry",
]
