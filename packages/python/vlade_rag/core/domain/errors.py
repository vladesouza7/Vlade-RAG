"""Domain errors. Interfaces map them to HTTP and MCP codes (docs/ARCHITECTURE.md section 4.4)."""

from __future__ import annotations


class VladeError(Exception):
    """Base class of every error raised by the framework on purpose."""

    code: str = "internal"
    http_status: int = 500
    retryable: bool = False

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFound(VladeError):
    """The entity does not exist in the tenant. Also used for entities of other tenants."""

    code = "not_found"
    http_status = 404


class PermissionDenied(VladeError):
    code = "forbidden"
    http_status = 403


class InvalidArgument(VladeError):
    code = "invalid_argument"
    http_status = 422


class UnsupportedFilter(InvalidArgument):
    """The adapter cannot translate the metadata filter."""


class Conflict(VladeError):
    code = "conflict"
    http_status = 409


class EmbeddingSpaceChanged(Conflict):
    """The active embedding space of the base changed while a document was indexed (reindex)."""


class MissingVectors(Conflict):
    """Some published chunks have no vector in the space a reindex wants to activate."""


class QuotaExceeded(VladeError):
    code = "quota_exceeded"
    http_status = 413


class RequestQuotaExceeded(QuotaExceeded):
    """The tenant used every request of its daily quota."""

    http_status = 429
    retryable = True


class RateLimited(VladeError):
    code = "rate_limited"
    http_status = 429
    retryable = True


class ProviderUnavailable(VladeError):
    """An external provider failed after the configured retries."""

    code = "unavailable"
    http_status = 503
    retryable = True


class Unauthenticated(VladeError):
    code = "unauthenticated"
    http_status = 401
