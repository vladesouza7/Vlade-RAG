"""The S3 object storage: adapter details and the runtime with ``backend = s3`` (roadmap 2.4).

Uses ``moto``, an in-process S3. No service and no network.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("boto3")
pytest.importorskip("moto")

import boto3
from moto import mock_aws

from vlade_rag.bootstrap import build_runtime
from vlade_rag.core.application import (
    CreateKnowledgeBase,
    DeleteDocument,
    GetDocument,
    SubmitIngestion,
)
from vlade_rag.core.config import Settings
from vlade_rag.core.config.settings import S3Settings
from vlade_rag.core.domain import InvalidArgument, ProviderUnavailable, RawDocument, Role, uuid7
from vlade_rag.core.domain.tenancy import TenantContext
from vlade_rag.ingestion.worker import Worker
from vlade_rag.knowledge.s3 import S3ObjectStorage

pytestmark = pytest.mark.anyio

BUCKET = "vlade-objects"
KB_CONFIG = {
    "embeddings": {"provider": "hashing", "model": "hashing-v1", "dimension": 64},
    "generation": {"provider": "extractive", "model": "extractive"},
}


@pytest.fixture(autouse=True)
def fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "testing")


@pytest.fixture
def aws() -> Iterator[Any]:
    with mock_aws():
        yield boto3.client("s3", region_name="us-east-1")


def settings(**kw: Any) -> S3Settings:
    return S3Settings(bucket=BUCKET, access_key_id="testing", secret_access_key="testing", **kw)  # type: ignore[arg-type]


def ctx() -> TenantContext:
    return TenantContext(uuid7(), uuid7(), frozenset({Role.ADMIN}), "library")


# ---------------------------------------------------------------- adapter


async def test_objects_live_under_the_tenant_prefix_with_their_content_type(aws: Any) -> None:
    aws.create_bucket(Bucket=BUCKET)
    storage = S3ObjectStorage.from_settings(settings())
    tenant = ctx()
    await storage.put(tenant, "kb/1/docs/2/original", b"# Titulo", "text/markdown")
    key = f"{tenant.tenant_id}/kb/1/docs/2/original"
    head = aws.head_object(Bucket=BUCKET, Key=key)
    assert head["ContentType"] == "text/markdown"
    assert [o["Key"] for o in aws.list_objects_v2(Bucket=BUCKET)["Contents"]] == [key]


async def test_ensure_bucket_creates_it_once_and_in_the_configured_region(aws: Any) -> None:
    storage = S3ObjectStorage.from_settings(settings(region="sa-east-1"))
    await storage.ensure_bucket()
    await storage.ensure_bucket()  # the second call changes nothing
    location = aws.get_bucket_location(Bucket=BUCKET)["LocationConstraint"]
    assert location == "sa-east-1"
    await storage.ping()


async def test_ping_fails_when_the_bucket_does_not_exist(aws: Any) -> None:
    storage = S3ObjectStorage.from_settings(settings())
    with pytest.raises(ProviderUnavailable):
        await storage.ping()


async def test_a_service_that_does_not_answer_is_provider_unavailable() -> None:
    storage = S3ObjectStorage.from_settings(
        settings(endpoint_url="http://127.0.0.1:1", timeout=1)  # nothing listens on port 1
    )
    with pytest.raises(ProviderUnavailable) as caught:
        await storage.put(ctx(), "a/b", b"x", "text/plain")
    assert "127.0.0.1" not in str(caught.value)  # no internal detail in the message


def test_settings_treat_empty_values_as_unset() -> None:
    s3 = S3Settings(endpoint_url="", access_key_id="", secret_access_key="")  # type: ignore[arg-type]
    assert s3.endpoint_url is None and s3.access_key_id is None and s3.secret_access_key is None
    assert s3.path_style is True and s3.create_bucket is False


def test_the_empty_s3_variables_of_the_compose_file_are_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dev profile passes these variables empty. The default backend must not change."""
    env = {
        "VLADE_OBJECT_STORAGE__BACKEND": "filesystem",
        "VLADE_OBJECT_STORAGE__S3__BUCKET": "",
        "VLADE_OBJECT_STORAGE__S3__ENDPOINT_URL": "",
        "VLADE_OBJECT_STORAGE__S3__REGION": "us-east-1",
        "VLADE_OBJECT_STORAGE__S3__ACCESS_KEY_ID": "",
        "VLADE_OBJECT_STORAGE__S3__SECRET_ACCESS_KEY": "",
        "VLADE_OBJECT_STORAGE__S3__PATH_STYLE": "true",
        "VLADE_OBJECT_STORAGE__S3__CREATE_BUCKET": "false",
        "VLADE_PROVIDERS__GEMINI__API_KEY": "",
        "VLADE_PROVIDERS__GEMINI__EMBEDDING_DIMENSIONS": "false",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    loaded = Settings()
    assert loaded.object_storage.backend == "filesystem"
    assert loaded.object_storage.s3.bucket == "" and loaded.object_storage.s3.endpoint_url is None
    assert loaded.providers.gemini.api_key is None


# ---------------------------------------------------------------- runtime


def runtime_settings(**s3: Any) -> Settings:
    return Settings(
        storage={"backend": "memory"},  # type: ignore[arg-type]
        object_storage={  # type: ignore[arg-type]
            "backend": "s3",
            "s3": {
                "bucket": BUCKET,
                "access_key_id": "testing",
                "secret_access_key": "testing",
                **s3,
            },
        },
    )


async def test_the_s3_backend_needs_a_bucket() -> None:
    bad = Settings(storage={"backend": "memory"}, object_storage={"backend": "s3"})  # type: ignore[arg-type]
    with pytest.raises(InvalidArgument, match="S3__BUCKET"):
        await build_runtime(bad, load_plugins=False)


async def test_documents_are_stored_read_and_deleted_through_s3(aws: Any) -> None:
    runtime = await build_runtime(runtime_settings(create_bucket=True), load_plugins=False)
    try:
        await runtime.checks["object_storage"]()  # the readiness check reaches the bucket
        tenant = await runtime.tenants.create_tenant("s3-tenant", "S3")
        issued = await runtime.tenants.issue_api_key(
            tenant.id, principal_name="a", roles=frozenset({Role.ADMIN})
        )
        admin = await runtime.tenants.authenticate(issued.key, interface="library")
        await CreateKnowledgeBase(runtime.deps).execute(
            admin, slug="docs", name="Docs", config=KB_CONFIG
        )
        submitted = await SubmitIngestion(runtime.deps).execute(
            admin,
            knowledge_base="docs",
            raw=RawDocument(
                filename="trocas.md",
                mime_type="text/markdown",
                data="# Trocas\n\nO prazo de troca é de sete dias.".encode(),
            ),
        )
        await Worker(runtime, worker_id="test").run_until_idle()

        keys = [o["Key"] for o in aws.list_objects_v2(Bucket=BUCKET)["Contents"]]
        assert keys and all(k.startswith(f"{tenant.id}/kb/") for k in keys)
        assert any(k.endswith("/original") for k in keys)
        assert any(k.endswith("/text.md") for k in keys)  # the normalized text is stored too

        view = await GetDocument(runtime.deps).execute(
            admin, knowledge_base="docs", document_id=submitted.document.id, include_text=True
        )
        assert view.text is not None and "sete dias" in view.text

        report = await DeleteDocument(runtime.deps).execute(
            admin, knowledge_base="docs", document_id=submitted.document.id, confirm=True
        )
        assert report.executed
        assert aws.list_objects_v2(Bucket=BUCKET).get("Contents") is None  # no object is left
    finally:
        await runtime.aclose()
