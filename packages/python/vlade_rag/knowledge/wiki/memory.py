"""In-memory ``WikiStore`` for tests and demos."""

from __future__ import annotations

from vlade_rag.core.domain import InvalidArgument, TenantContext
from vlade_rag.knowledge.object_keys import validate_object_key


class MemoryWikiStore:
    def __init__(self) -> None:
        self.pages: dict[tuple[str, str], dict[str, str]] = {}

    @staticmethod
    def _key(ctx: TenantContext, knowledge_base: str) -> tuple[str, str]:
        validate_object_key(knowledge_base)
        return str(ctx.tenant_id), knowledge_base

    @staticmethod
    def _path(path: str) -> str:
        validate_object_key(path)
        return path.replace("\\", "/")

    async def list(self, ctx: TenantContext, knowledge_base: str) -> tuple[str, ...]:
        pages = self.pages.get(self._key(ctx, knowledge_base), {})
        return tuple(sorted(pages))

    async def get(self, ctx: TenantContext, knowledge_base: str, path: str) -> str | None:
        pages = self.pages.get(self._key(ctx, knowledge_base), {})
        return pages.get(self._path(path))

    async def put(self, ctx: TenantContext, knowledge_base: str, path: str, content: str) -> None:
        key = self._key(ctx, knowledge_base)
        self.pages.setdefault(key, {})[self._path(path)] = content

    async def delete(self, ctx: TenantContext, knowledge_base: str, path: str) -> None:
        pages = self.pages.get(self._key(ctx, knowledge_base))
        if pages is not None:
            pages.pop(self._path(path), None)


def _assert_wiki_path(path: str) -> None:
    """Reserved for adapters that need a stricter path check."""
    if not path or path.startswith("/"):
        raise InvalidArgument(f"Invalid wiki path '{path}'.")
