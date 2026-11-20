"""Validation of object keys, shared by the ``ObjectStorage`` adapters (ADR-0006).

An adapter prefixes every key with ``{tenant_id}/``. A key that climbs out of that folder, or one
that an HTTP client may normalize into another path, must never reach the storage.
"""

from __future__ import annotations

from vlade_rag.core.domain import InvalidArgument


def validate_object_key(key: str, *, prefix: bool = False) -> str:
    """Return the key without a trailing ``/`` (a prefix), or raise ``InvalidArgument``."""
    candidate = key.rstrip("/") if prefix else key
    segments = candidate.split("/")
    bad = (
        not candidate
        or candidate.startswith("/")
        or any(s in ("", ".", "..") for s in segments)
        or "\\" in candidate
        or any(ord(c) < 32 for c in candidate)
    )
    if bad:
        raise InvalidArgument(f"Invalid object key '{key}'.")
    return candidate
