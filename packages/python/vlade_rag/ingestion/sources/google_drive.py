"""Google Drive connector: list files of a folder and download them with the Drive API.

The connector uses an OAuth access token supplied by the operator. It needs only ``httpx2``;
the token refresh is the responsibility of the operator or of an external secret manager.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any
from urllib.parse import quote

import httpx2
from pydantic import SecretStr

from vlade_rag.core.domain import (
    InvalidArgument,
    ProviderUnavailable,
    RawDocument,
    SourceItem,
    TenantContext,
)

DEFAULT_API = "https://www.googleapis.com/drive/v3"


class GoogleDriveSource:
    """Read-only Drive adapter. One page of ``pageSize`` files per ``list_items`` call."""

    name = "google_drive"

    def __init__(
        self,
        access_token: SecretStr | None,
        *,
        folder_id: str = "root",
        page_size: int = 100,
        max_files: int = 1000,
        api_base: str = DEFAULT_API,
        timeout: float = 30.0,
        client_factory: Callable[[dict[str, str]], httpx2.AsyncClient] | None = None,
    ) -> None:
        self.token = access_token
        self.folder_id = folder_id
        self.page_size = page_size
        self.max_files = max_files
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self._client_factory = client_factory

    def _client(self) -> httpx2.AsyncClient:
        if self.token is None or not self.token.get_secret_value():
            raise InvalidArgument(
                "The Google Drive source needs VLADE_SOURCES__GOOGLE_DRIVE__ACCESS_TOKEN."
            )
        headers = {"Authorization": f"Bearer {self.token.get_secret_value()}"}
        if self._client_factory is not None:
            return self._client_factory(headers)
        return httpx2.AsyncClient(headers=headers, timeout=self.timeout)

    async def list_items(self, ctx: TenantContext, cursor: str | None) -> AsyncIterator[SourceItem]:
        params: dict[str, Any] = {
            "q": f"'{self.folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType,modifiedTime)",
            "pageSize": min(self.page_size, self.max_files),
        }
        if cursor:
            params["pageToken"] = cursor
        emitted = 0
        async with self._client() as client:
            while emitted < self.max_files:
                try:
                    response = await client.get(f"{self.api_base}/files", params=params)
                except httpx2.HTTPError as exc:
                    raise ProviderUnavailable("Google Drive is not reachable.") from exc
                if response.status_code >= 400:
                    raise ProviderUnavailable(f"Google Drive returned HTTP {response.status_code}.")
                payload = response.json()
                for entry in payload.get("files", []):
                    file_id = str(entry.get("id", ""))
                    if not file_id:
                        continue
                    yield SourceItem(
                        uri=f"gdrive://{file_id}",
                        filename=str(entry.get("name") or file_id),
                        mime_type=entry.get("mimeType"),
                        external_id=file_id,
                        metadata={
                            "drive_id": file_id,
                            "modified_time": str(entry.get("modifiedTime") or ""),
                        },
                    )
                    emitted += 1
                    if emitted >= self.max_files:
                        return
                token = payload.get("nextPageToken")
                if not token:
                    return
                params["pageToken"] = token

    async def fetch(self, ctx: TenantContext, item: SourceItem) -> RawDocument:
        file_id = str(item.metadata.get("drive_id") or item.external_id or "")
        if not file_id:
            raise InvalidArgument("The Drive item has no file id.")
        async with self._client() as client:
            try:
                response = await client.get(
                    f"{self.api_base}/files/{quote(file_id, safe='')}", params={"alt": "media"}
                )
            except httpx2.HTTPError as exc:
                raise ProviderUnavailable("Google Drive is not reachable.") from exc
        if response.status_code == 404:
            raise InvalidArgument("The Drive file does not exist.")
        if response.status_code >= 400:
            raise ProviderUnavailable(f"Google Drive returned HTTP {response.status_code}.")
        return RawDocument(
            filename=item.filename,
            mime_type=item.mime_type or response.headers.get("content-type", "").split(";")[0],
            data=response.content,
            source_type="gdrive",
            source_uri=item.uri,
            metadata=dict(item.metadata),
        )


__all__ = ["GoogleDriveSource"]
