"""``WikiStore`` on the local filesystem. Layout: ``<root>/<tenant>/<base>/<path>``.

Paths are bundle-relative POSIX paths. A tenant never sees another tenant's directory.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from vlade_rag.core.domain import InvalidArgument, TenantContext
from vlade_rag.knowledge.object_keys import validate_object_key


class FileSystemWikiStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _base(self, ctx: TenantContext, knowledge_base: str) -> Path:
        validate_object_key(knowledge_base)
        return (self.root / str(ctx.tenant_id) / knowledge_base).resolve()

    def _path(self, ctx: TenantContext, knowledge_base: str, path: str) -> Path:
        validate_object_key(path)
        base = self._base(ctx, knowledge_base)
        target = (base / path).resolve()
        if base != target.parent and base not in target.parents:
            raise InvalidArgument(f"Invalid wiki path '{path}'.")
        return target

    async def list(self, ctx: TenantContext, knowledge_base: str) -> tuple[str, ...]:
        base = self._base(ctx, knowledge_base)

        def _list() -> tuple[str, ...]:
            if not base.exists():
                return ()
            return tuple(
                sorted(file.relative_to(base).as_posix() for file in base.rglob("*.md"))
            )

        return await asyncio.to_thread(_list)

    async def get(self, ctx: TenantContext, knowledge_base: str, path: str) -> str | None:
        target = self._path(ctx, knowledge_base, path)
        try:
            return await asyncio.to_thread(target.read_text, encoding="utf-8")
        except FileNotFoundError:
            return None

    async def put(
        self, ctx: TenantContext, knowledge_base: str, path: str, content: str
    ) -> None:
        target = self._path(ctx, knowledge_base, path)

        def _write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, target)

        await asyncio.to_thread(_write)

    async def delete(self, ctx: TenantContext, knowledge_base: str, path: str) -> None:
        target = self._path(ctx, knowledge_base, path)
        try:
            await asyncio.to_thread(target.unlink)
        except FileNotFoundError:
            return
