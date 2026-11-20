"""ObjectStorage on the S3 API (docs/adr/0006-armazenamento-de-objetos.md).

Works with AWS S3 and with any S3-compatible service. Layout: ``s3://<bucket>/<tenant_id>/<key>``.
The adapter uses ``boto3`` (Apache-2.0) in worker threads, so the event loop never blocks.

A failure of the service (network, credentials, server error) is a ``ProviderUnavailable``. A
missing object is a ``NotFound``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from vlade_rag.core.config.settings import S3Settings
from vlade_rag.core.domain import NotFound, ProviderUnavailable, TenantContext
from vlade_rag.knowledge.object_keys import validate_object_key

logger = logging.getLogger(__name__)

T = TypeVar("T")
_MISSING = {"NoSuchKey", "404", "NotFound"}
_BATCH = 1000  # DeleteObjects accepts at most 1000 keys


def _code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


class S3ObjectStorage:
    def __init__(self, client: Any, bucket: str, *, region: str = "us-east-1") -> None:
        self.client = client
        self.bucket = bucket
        self.region = region

    @classmethod
    def from_settings(cls, settings: S3Settings) -> S3ObjectStorage:
        config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.path_style else "auto"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=settings.timeout,
            read_timeout=settings.timeout,
            # Send a checksum only when the operation requires one. Several S3-compatible
            # services reject the default checksum trailer of recent boto3 versions.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
        client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            region_name=settings.region,
            aws_access_key_id=None
            if settings.access_key_id is None
            else settings.access_key_id.get_secret_value(),
            aws_secret_access_key=None
            if settings.secret_access_key is None
            else settings.secret_access_key.get_secret_value(),
            config=config,
        )
        return cls(client, settings.bucket, region=settings.region)

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _key(ctx: TenantContext, key: str) -> str:
        return f"{ctx.tenant_id}/{validate_object_key(key)}"

    @staticmethod
    def _prefix(ctx: TenantContext, prefix: str) -> str:
        return f"{ctx.tenant_id}/{validate_object_key(prefix, prefix=True)}/"

    async def _call(self, fn: Callable[[], T]) -> T:
        try:
            return await asyncio.to_thread(fn)
        except ClientError as exc:
            if _code(exc) in _MISSING:
                raise
            logger.warning("S3 request failed: %s", _code(exc) or exc.__class__.__name__)
            raise ProviderUnavailable("The object storage is not available.") from exc
        except BotoCoreError as exc:
            logger.warning("S3 request failed: %s", exc.__class__.__name__)
            raise ProviderUnavailable("The object storage is not available.") from exc

    # ------------------------------------------------------------ ObjectStorage

    async def put(self, ctx: TenantContext, key: str, data: bytes, content_type: str) -> None:
        full = self._key(ctx, key)
        await self._call(
            lambda: self.client.put_object(
                Bucket=self.bucket, Key=full, Body=data, ContentType=content_type or ""
            )
        )

    async def get(self, ctx: TenantContext, key: str) -> bytes:
        full = self._key(ctx, key)

        def read() -> bytes:
            return bytes(self.client.get_object(Bucket=self.bucket, Key=full)["Body"].read())

        try:
            return await self._call(read)
        except ClientError:
            raise NotFound(f"Object '{key}' does not exist.") from None

    async def delete(self, ctx: TenantContext, key: str) -> None:
        full = self._key(ctx, key)
        await self._call(lambda: self.client.delete_object(Bucket=self.bucket, Key=full))

    async def delete_prefix(self, ctx: TenantContext, prefix: str) -> int:
        """Delete every object whose key starts with ``prefix/``. Return how many."""
        start = self._prefix(ctx, prefix)

        def remove() -> int:
            deleted = 0
            pages = self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=start
            )
            for page in pages:
                keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                for i in range(0, len(keys), _BATCH):
                    batch = keys[i : i + _BATCH]
                    result = self.client.delete_objects(
                        Bucket=self.bucket, Delete={"Objects": batch, "Quiet": True}
                    )
                    deleted += len(batch) - len(result.get("Errors", []))
            return deleted

        return await self._call(remove)

    # ------------------------------------------------------------ operations

    async def ping(self) -> None:
        """Raise ``ProviderUnavailable`` if the bucket is not reachable (readiness check)."""
        try:
            await self._call(lambda: self.client.head_bucket(Bucket=self.bucket))
        except ClientError as exc:
            raise ProviderUnavailable("The object storage bucket does not exist.") from exc

    async def ensure_bucket(self) -> None:
        """Create the bucket if it does not exist. Use it for a local service, not for the cloud."""

        def create() -> None:
            try:
                self.client.head_bucket(Bucket=self.bucket)
                return
            except ClientError as exc:
                if _code(exc) not in _MISSING:
                    raise
            args: dict[str, Any] = {"Bucket": self.bucket}
            if self.region != "us-east-1":  # AWS rejects a LocationConstraint for us-east-1
                args["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
            self.client.create_bucket(**args)

        await self._call(create)
