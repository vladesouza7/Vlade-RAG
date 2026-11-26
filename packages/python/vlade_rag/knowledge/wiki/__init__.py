"""Adapters of the ``WikiStore`` port (phase 6, task 6.12)."""

from __future__ import annotations

from vlade_rag.knowledge.wiki.filesystem import FileSystemWikiStore
from vlade_rag.knowledge.wiki.memory import MemoryWikiStore

__all__ = ["FileSystemWikiStore", "MemoryWikiStore"]
