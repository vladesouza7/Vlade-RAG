"""Contract of the ``ObjectStorage`` port: memory, filesystem and S3 run the same tests.

The S3 run uses ``moto`` (an in-process S3), so it needs no service. To run the same tests against a
real S3-compatible service, set ``VLADE_TEST_S3_ENDPOINT``, ``VLADE_TEST_S3_BUCKET``,
``VLADE_TEST_S3_ACCESS_KEY`` and ``VLADE_TEST_S3_SECRET_KEY`` (the bucket must exist).
Every test uses new tenant ids, so it never reads the objects of another test.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

pytest.importorskip("boto3")
pytest.importorskip("moto")

import boto3
from moto import mock_aws

from vlade_rag.core.config.settings import S3Settings
from vlade_rag.core.domain import InvalidArgument, NotFound, Role, TenantContext, uuid7
from vlade_rag.core.ports import ObjectStorage
from vlade_rag.knowledge.filesystem import FilesystemObjectStorage
from vlade_rag.knowledge.memory import MemoryObjectStorage, MemoryStore
from vlade_rag.knowledge.s3 import S3ObjectStorage

pytestmark = pytest.mark.anyio

BUCKET = "vlade-test"
LIVE_ENV = ("VLADE_TEST_S3_ENDPOINT", "VLADE_TEST_S3_BUCKET")


def make_ctx() -> TenantContext:
    return TenantContext(uuid7(), uuid7(), frozenset({Role.ADMIN}), "library")


@pytest.fixture
def moto_s3(monkeypatch: pytest.MonkeyPatch) -> Iterator[S3ObjectStorage]:
    """An S3ObjectStorage on an in-process S3 with an empty bucket."""
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "testing")  # moto never sees a real credential
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield S3ObjectStorage.from_settings(
            S3Settings(bucket=BUCKET, access_key_id="testing", secret_access_key="testing")  # type: ignore[arg-type]
        )


@pytest.fixture(
    params=["memory", "filesystem", "s3", pytest.param("s3-live", marks=pytest.mark.integration)]
)
async def storage(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[ObjectStorage]:
    if request.param == "memory":
        yield MemoryObjectStorage(MemoryStore())
    elif request.param == "filesystem":
        yield FilesystemObjectStorage(tmp_path)
    elif request.param == "s3":
        yield request.getfixturevalue("moto_s3")
    else:
        if not all(os.environ.get(v) for v in LIVE_ENV):
            pytest.skip(f"{', '.join(LIVE_ENV)} are not set")
        yield S3ObjectStorage.from_settings(
            S3Settings(
                bucket=os.environ["VLADE_TEST_S3_BUCKET"],
                endpoint_url=os.environ["VLADE_TEST_S3_ENDPOINT"],
                access_key_id=os.environ.get("VLADE_TEST_S3_ACCESS_KEY"),  # type: ignore[arg-type]
                secret_access_key=os.environ.get("VLADE_TEST_S3_SECRET_KEY"),  # type: ignore[arg-type]
            )
        )


async def test_round_trip_and_overwrite(storage: ObjectStorage) -> None:
    ctx = make_ctx()
    data = bytes(range(256)) + b"\x00\xff" * 100  # binary, with zero bytes
    await storage.put(ctx, "kb/1/docs/2/original", data, "application/octet-stream")
    assert await storage.get(ctx, "kb/1/docs/2/original") == data
    await storage.put(ctx, "kb/1/docs/2/original", b"newer", "text/plain")
    assert await storage.get(ctx, "kb/1/docs/2/original") == b"newer"
    await storage.put(ctx, "kb/1/docs/2/empty", b"", "text/plain")
    assert await storage.get(ctx, "kb/1/docs/2/empty") == b""


async def test_a_missing_object_is_not_found(storage: ObjectStorage) -> None:
    with pytest.raises(NotFound):
        await storage.get(make_ctx(), "kb/1/docs/2/missing")


async def test_delete_is_idempotent(storage: ObjectStorage) -> None:
    ctx = make_ctx()
    await storage.put(ctx, "a/b", b"x", "text/plain")
    await storage.delete(ctx, "a/b")
    await storage.delete(ctx, "a/b")  # no error the second time
    await storage.delete(ctx, "never/existed")
    with pytest.raises(NotFound):
        await storage.get(ctx, "a/b")


async def test_delete_prefix_removes_only_that_folder(storage: ObjectStorage) -> None:
    ctx = make_ctx()
    for key in (
        "kb/1/docs/2/original",
        "kb/1/docs/2/text.md",
        "kb/1/docs/2/v2/original",
        "kb/1/docs/20/original",  # a sibling whose name starts like the prefix
        "kb/1/docs/3/original",
    ):
        await storage.put(ctx, key, b"x", "text/plain")
    assert await storage.delete_prefix(ctx, "kb/1/docs/2/") == 3
    for gone in ("kb/1/docs/2/original", "kb/1/docs/2/text.md", "kb/1/docs/2/v2/original"):
        with pytest.raises(NotFound):
            await storage.get(ctx, gone)
    assert await storage.get(ctx, "kb/1/docs/20/original") == b"x"
    assert await storage.get(ctx, "kb/1/docs/3/original") == b"x"
    assert await storage.delete_prefix(ctx, "kb/1/docs/2/") == 0
    assert await storage.delete_prefix(ctx, "nothing/here/") == 0


async def test_delete_prefix_handles_more_than_one_batch(storage: ObjectStorage) -> None:
    """S3 deletes at most 1000 keys per request."""
    ctx = make_ctx()
    for i in range(1005):
        await storage.put(ctx, f"many/{i:04d}", b"x", "text/plain")
    await storage.put(ctx, "keep/this", b"x", "text/plain")
    assert await storage.delete_prefix(ctx, "many/") == 1005
    assert await storage.get(ctx, "keep/this") == b"x"
    with pytest.raises(NotFound):
        await storage.get(ctx, "many/0000")


async def test_objects_are_tenant_scoped(storage: ObjectStorage) -> None:
    a, b = make_ctx(), make_ctx()
    await storage.put(a, "kb/1/docs/2/original", b"secret-of-a", "text/plain")
    with pytest.raises(NotFound):
        await storage.get(b, "kb/1/docs/2/original")
    await storage.put(b, "kb/1/docs/2/original", b"b", "text/plain")
    assert await storage.get(a, "kb/1/docs/2/original") == b"secret-of-a"
    assert await storage.delete_prefix(b, "kb/1/docs/2/") == 1  # only the object of b
    assert await storage.get(a, "kb/1/docs/2/original") == b"secret-of-a"
    await storage.delete(b, "kb/1/docs/2/original")
    assert await storage.get(a, "kb/1/docs/2/original") == b"secret-of-a"


@pytest.mark.parametrize(
    "key",
    ["../other", "/absolute", "a/../b", "a/./b", "a//b", "", "a\\b", "a/\x00b", ".."],
)
async def test_unsafe_keys_are_refused(storage: ObjectStorage, key: str) -> None:
    ctx = make_ctx()
    with pytest.raises(InvalidArgument):
        await storage.put(ctx, key, b"x", "text/plain")
    with pytest.raises(InvalidArgument):
        await storage.get(ctx, key)
    with pytest.raises(InvalidArgument):
        await storage.delete(ctx, key)


@pytest.mark.parametrize("prefix", ["", "/", "../x/", "a/../b/", "a//b/"])
async def test_unsafe_prefixes_are_refused(storage: ObjectStorage, prefix: str) -> None:
    with pytest.raises(InvalidArgument):
        await storage.delete_prefix(make_ctx(), prefix)
