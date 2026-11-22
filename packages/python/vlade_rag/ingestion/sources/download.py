"""Download of a document from an origin URI (ARCHITECTURE section 15, MCP_SPEC section 5.7).

``s3://`` reads an object of the tenant bucket. ``https://`` reads a public address of an allowed
domain. The download never follows a redirect, refuses a host that resolves to a private or
link-local address, and stops above the size limit.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx2

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import (
    InvalidArgument,
    NotFound,
    ProviderUnavailable,
    QuotaExceeded,
    TenantContext,
)

HTTPS_PORT = 443


@dataclass(frozen=True, slots=True)
class SourceContent:
    data: bytes
    mime_type: str | None = None


def host_allowed(host: str, allowed_domains: Sequence[str]) -> bool:
    """True when ``host`` is an allowed domain or a subdomain of one."""
    name = host.rstrip(".").lower()
    for domain in allowed_domains:
        allowed = domain.strip().rstrip(".").lower()
        if allowed and (name == allowed or name.endswith(f".{allowed}")):
            return True
    return False


async def read_source(deps: Dependencies, ctx: TenantContext, uri: str) -> SourceContent:
    """Read ``uri`` and return its bytes and the declared MIME type, if any."""
    scheme = urlsplit(uri).scheme.lower()
    if scheme == "s3":
        return await _from_s3(deps, ctx, uri)
    if scheme == "https":
        return await _from_https(deps, uri)
    raise InvalidArgument("The source_uri must use s3:// or https://.")


# ---------------------------------------------------------------- s3


async def _from_s3(deps: Dependencies, ctx: TenantContext, uri: str) -> SourceContent:
    parts = urlsplit(uri)
    bucket = parts.netloc
    key = parts.path.lstrip("/")
    if not bucket or not key:
        raise InvalidArgument("The source_uri must have a bucket and an object key.")
    configured = getattr(deps.object_storage, "bucket", None)
    if configured is None:
        raise InvalidArgument(
            "This server reads s3:// only when the object storage uses the S3 backend."
        )
    if bucket != configured:
        raise InvalidArgument("The source_uri must use the bucket of this server.")
    prefix = f"{ctx.tenant_id}/"
    if not key.startswith(prefix):
        raise InvalidArgument("The source_uri must point to an object of the tenant.")
    try:
        data = await deps.object_storage.get(ctx, key[len(prefix) :])
    except NotFound:
        raise NotFound("The source object does not exist.") from None
    return SourceContent(data)


# ---------------------------------------------------------------- https


async def _from_https(deps: Dependencies, uri: str) -> SourceContent:
    policy = deps.sources
    if not policy.allowed_domains:
        raise InvalidArgument(
            "The server does not allow https:// sources. Set VLADE_SOURCES__ALLOWED_DOMAINS."
        )
    parts = urlsplit(uri)
    if parts.username is not None or parts.password is not None:
        raise InvalidArgument("The source_uri must not carry a user name or a password.")
    host = parts.hostname
    if host is None or not host_allowed(host, policy.allowed_domains):
        raise InvalidArgument("The host of the source_uri is not in the allowed domains.")
    if (parts.port or HTTPS_PORT) != HTTPS_PORT:
        raise InvalidArgument("The source_uri must use port 443.")
    await _check_public(host)

    limit = min(policy.max_bytes, deps.limits.max_upload_bytes)
    try:
        async with (
            httpx2.AsyncClient(
                follow_redirects=False, timeout=httpx2.Timeout(policy.timeout, connect=10.0)
            ) as client,
            client.stream("GET", uri) as response,
        ):
            if response.is_redirect:
                raise InvalidArgument("The source_uri must not redirect.")
            if response.status_code == 404:
                raise NotFound("The source URI does not exist.")
            if response.status_code >= 400:
                raise ProviderUnavailable(f"The source URI returned HTTP {response.status_code}.")
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > limit:
                    raise QuotaExceeded(f"The source has more than {limit} bytes.")
                chunks.append(chunk)
            declared = response.headers.get("content-type", "").split(";")[0].strip()
    except httpx2.HTTPError as exc:
        raise ProviderUnavailable("The source URI is not reachable.") from exc
    return SourceContent(b"".join(chunks), declared or None)


async def _check_public(host: str) -> None:
    """Refuse a host that resolves to a private, loopback, link-local or reserved address."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, HTTPS_PORT, type=socket.SOCK_STREAM
        )
    except OSError:
        raise ProviderUnavailable("The source host does not resolve.") from None
    for info in infos:
        address = str(info[4][0]).split("%")[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise InvalidArgument("The source host does not resolve to an IP address.") from None
        if not ip.is_global or ip.is_multicast:
            raise InvalidArgument("The source host resolves to a private or link-local address.")
