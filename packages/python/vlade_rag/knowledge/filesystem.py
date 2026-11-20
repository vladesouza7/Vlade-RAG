"""ObjectStorage on the local filesystem (``dev`` profile, ADR-0006).

Layout: ``<root>/<tenant_id>/<key>``. Keys must be relative and must not contain ``..``.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from vlade_rag.core.domain import InvalidArgument, NotFound, TenantContext
from vlade_rag.knowledge.object_keys import validate_object_key


class FilesystemObjectStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, ctx: TenantContext, key: str) -> Path:
        validate_object_key(key)
        base = (self.root / str(ctx.tenant_id)).resolve()
        path = (base / key).resolve()
        if base not in path.parents:
            raise InvalidArgument(f"Invalid object key '{key}'.")
        return path

    async def put(self, ctx: TenantContext, key: str, data: bytes, content_type: str) -> None:
        path = self._path(ctx, key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)

        await asyncio.to_thread(_write)

    async def get(self, ctx: TenantContext, key: str) -> bytes:
        path = self._path(ctx, key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            raise NotFound(f"Object '{key}' does not exist.") from None

    async def delete(self, ctx: TenantContext, key: str) -> None:
        path = self._path(ctx, key)
        await asyncio.to_thread(path.unlink, True)

    async def delete_prefix(self, ctx: TenantContext, prefix: str) -> int:
        directory = self._path(ctx, validate_object_key(prefix, prefix=True))

        def _remove() -> int:
            if not directory.exists():
                return 0
            count = sum(1 for p in directory.rglob("*") if p.is_file())
            shutil.rmtree(directory)
            return count

        return await asyncio.to_thread(_remove)
