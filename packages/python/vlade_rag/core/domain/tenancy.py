"""Tenant context and roles (docs/ARCHITECTURE.md section 4.1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from vlade_rag.core.domain.errors import PermissionDenied


class Role(StrEnum):
    READER = "reader"
    WRITER = "writer"
    ADMIN = "admin"


_RANK = {Role.READER: 1, Role.WRITER: 2, Role.ADMIN: 3}

Interface = Literal["api", "mcp", "cli", "worker", "library"]


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Who is calling, for which tenant. Interfaces build it from the credential only."""

    tenant_id: UUID
    principal_id: UUID
    roles: frozenset[Role]
    interface: Interface
    trace_id: str | None = None

    def has(self, role: Role) -> bool:
        """``admin`` includes ``writer``, ``writer`` includes ``reader``."""
        needed = _RANK[role]
        return any(_RANK[r] >= needed for r in self.roles)

    def require(self, role: Role) -> None:
        if not self.has(role):
            raise PermissionDenied(f"Role '{role.value}' is required.")

    def as_worker(self) -> TenantContext:
        """Context used by the ingestion worker for a job of this tenant."""
        return TenantContext(
            tenant_id=self.tenant_id,
            principal_id=self.principal_id,
            roles=frozenset({Role.ADMIN}),
            interface="worker",
            trace_id=self.trace_id,
        )
