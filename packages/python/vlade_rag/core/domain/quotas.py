"""Tenant quotas (docs/ARCHITECTURE.md section 15).

The limits live in ``tenants.settings["quotas"]``. A missing limit means "unlimited".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from vlade_rag.core.domain.errors import InvalidArgument, QuotaExceeded


@dataclass(frozen=True, slots=True)
class TenantUsage:
    """What a tenant stores now. Bytes count versions in ``indexing`` and ``published``."""

    documents: int = 0
    bytes: int = 0


def _limit(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidArgument(f"The quota '{name}' must be a whole number of 0 or more.")
    return value


@dataclass(frozen=True, slots=True)
class TenantQuotas:
    """Limits of a tenant. ``None`` means no limit."""

    documents: int | None = None
    bytes: int | None = None

    def __post_init__(self) -> None:
        _limit(self.documents, "documents")
        _limit(self.bytes, "bytes")

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> TenantQuotas:
        raw = settings.get("quotas") or {}
        return cls(
            documents=_limit(raw.get("documents"), "documents"),
            bytes=_limit(raw.get("bytes"), "bytes"),
        )

    def to_settings(self) -> dict[str, int]:
        out: dict[str, int] = {}
        if self.documents is not None:
            out["documents"] = self.documents
        if self.bytes is not None:
            out["bytes"] = self.bytes
        return out

    def check_submit(self, usage: TenantUsage, *, new_document: bool, added_bytes: int) -> None:
        """Raise ``QuotaExceeded`` if storing the file would pass a limit."""
        if new_document and self.documents is not None and usage.documents + 1 > self.documents:
            raise QuotaExceeded(
                f"The tenant has {usage.documents} documents; the quota is {self.documents}."
            )
        if self.bytes is not None and usage.bytes + added_bytes > self.bytes:
            raise QuotaExceeded(
                f"The file has {added_bytes} bytes and the tenant already stores {usage.bytes} "
                f"bytes; the quota is {self.bytes} bytes."
            )
