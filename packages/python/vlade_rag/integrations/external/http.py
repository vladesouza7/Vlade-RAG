"""Shared HTTP client for provider adapters: JSON requests, retries and error mapping."""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import httpx2

from vlade_rag.core.domain import InvalidArgument, ProviderUnavailable

RETRY_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class ProviderHttpClient:
    """Thin wrapper around ``httpx2.AsyncClient`` with retries and domain errors."""

    def __init__(
        self,
        provider: str,
        base_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 120.0,
        retries: int = 3,
        backoff: float = 0.5,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.provider = provider
        self.retries = retries
        self.backoff = backoff
        self.client = httpx2.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=dict(headers or {}),
            timeout=httpx2.Timeout(timeout, connect=10.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    def _error(self, response: httpx2.Response) -> Exception:
        detail = response.text[:300]
        message = f"{self.provider} returned HTTP {response.status_code}: {detail}"
        if response.status_code in (400, 404, 422):
            return InvalidArgument(message)
        return ProviderUnavailable(message)

    async def _sleep(self, attempt: int) -> None:
        await asyncio.sleep(self.backoff * (2**attempt) * (0.5 + random.random()))  # noqa: S311

    async def post_json(self, path: str, payload: Mapping[str, Any]) -> Any:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = await self.client.post(path, json=payload)
            except httpx2.TransportError as exc:
                last = ProviderUnavailable(f"{self.provider} is unreachable: {exc!r}")
            else:
                if response.status_code < 400:
                    return response.json()
                last = self._error(response)
                if response.status_code not in RETRY_STATUS:
                    raise last
            if attempt < self.retries:
                await self._sleep(attempt)
        assert last is not None  # noqa: S101 - loop always sets it
        raise last

    @asynccontextmanager
    async def stream_lines(
        self, path: str, payload: Mapping[str, Any]
    ) -> AsyncIterator[AsyncIterator[str]]:
        """POST and yield the response lines. Retries only before the first byte."""
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with self.client.stream("POST", path, json=payload) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        last = self._error(response)
                        if response.status_code not in RETRY_STATUS:
                            raise last
                    else:
                        yield response.aiter_lines()
                        return
            except httpx2.TransportError as exc:
                last = ProviderUnavailable(f"{self.provider} is unreachable: {exc!r}")
            if attempt < self.retries:
                await self._sleep(attempt)
        assert last is not None  # noqa: S101
        raise last


def parse_sse_data(line: str) -> dict[str, Any] | None:
    """Parse one ``data: {...}`` Server-Sent Events line. Returns None for other lines."""
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data or data == "[DONE]":
        return None
    parsed: dict[str, Any] = json.loads(data)
    return parsed
