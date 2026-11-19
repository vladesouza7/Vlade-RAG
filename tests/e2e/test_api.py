"""REST API end to end, in process. Runs with the memory and the PostgreSQL runtime."""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from vlade_rag.api.app import create_app
from vlade_rag.bootstrap import Runtime, build_runtime
from vlade_rag.core.config import Settings
from vlade_rag.core.domain import Role
from vlade_rag.ingestion.worker import Worker

KB_CONFIG = {
    "chunking": {"strategy": "markdown", "max_tokens": 60, "overlap_tokens": 5},
    "embeddings": {"provider": "hashing", "model": "hashing-v1", "dimension": 64},
    "generation": {"provider": "extractive", "model": "extractive"},
}
DOC = """# Política de Trocas

## Prazo

O cliente pode trocar o produto em até sete dias corridos após o recebimento.

## Condições

O produto deve estar sem uso e na embalagem original.
"""


@dataclass
class Api:
    client: TestClient
    runtime: Runtime
    admin: dict[str, str]
    reader: dict[str, str]
    other: dict[str, str]

    def drain(self) -> int:
        return int(self.client.portal.call(Worker(self.runtime, worker_id="t").run_until_idle))  # type: ignore[union-attr]


def _settings(backend: str, request: pytest.FixtureRequest) -> Settings:
    if backend == "memory":
        return Settings(
            storage={"backend": "memory"},  # type: ignore[arg-type]
            object_storage={"backend": "memory"},  # type: ignore[arg-type]
        )
    _, app_url = request.getfixturevalue("postgres_urls")
    return Settings(
        database={"url": app_url},  # type: ignore[arg-type]
        security={"api_key_pepper": "test-pepper"},  # type: ignore[arg-type]
        object_storage={"backend": "memory"},  # type: ignore[arg-type]
    )


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.integration)])
def api(request: pytest.FixtureRequest) -> Iterator[Api]:
    settings = _settings(request.param, request)
    holder: dict[str, Any] = {}

    async def setup() -> dict[str, str]:
        rt = await build_runtime(settings, load_plugins=False)
        holder["rt"] = rt
        suffix = secrets.token_hex(3)
        acme = await rt.tenants.create_tenant(f"acme-{suffix}", "ACME")
        globex = await rt.tenants.create_tenant(f"globex-{suffix}", "Globex")
        issue = rt.tenants.issue_api_key
        return {
            "admin": (await issue(acme.id, principal_name="a", roles=frozenset({Role.ADMIN}))).key,
            "reader": (
                await issue(acme.id, principal_name="r", roles=frozenset({Role.READER}))
            ).key,
            "other": (
                await issue(globex.id, principal_name="o", roles=frozenset({Role.ADMIN}))
            ).key,
        }

    app = create_app(settings, runtime=None)
    with TestClient(app) as client:
        keys = client.portal.call(setup)  # type: ignore[union-attr]
        runtime: Runtime = holder["rt"]
        app.state.runtime = runtime
        try:
            yield Api(
                client,
                runtime,
                *({"Authorization": f"Bearer {keys[k]}"} for k in ("admin", "reader", "other")),
            )
        finally:
            client.portal.call(runtime.aclose)  # type: ignore[union-attr]


def _load(api: Api) -> str:
    r = api.client.post(
        "/v1/knowledge-bases",
        json={"slug": "trocas", "name": "Trocas", "config": KB_CONFIG},
        headers=api.admin,
    )
    assert r.status_code == 201, r.text
    r = api.client.post(
        "/v1/knowledge-bases/trocas/documents",
        files={"file": ("trocas.md", DOC.encode(), "text/markdown")},
        data={"metadata": json.dumps({"area": "pos-venda"}), "external_id": "trocas"},
        headers=api.admin,
    )
    assert r.status_code == 202, r.text
    assert api.drain() == 1
    job = api.client.get(f"/v1/jobs/{r.json()['job']['id']}", headers=api.reader).json()
    assert job["status"] == "succeeded", job
    return str(r.json()["document_id"])


def test_health(api: Api) -> None:
    assert api.client.get("/health/live").json()["status"] == "ok"
    assert api.client.get("/health/ready").json() == {"status": "ok"}


def test_authentication_errors_use_problem_json(api: Api) -> None:
    r = api.client.get("/v1/knowledge-bases")
    assert r.status_code == 401
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "unauthenticated"
    bad = api.client.get("/v1/knowledge-bases", headers={"Authorization": "Bearer vrag_x_y"})
    assert bad.status_code == 401


def test_full_flow(api: Api) -> None:
    doc_id = _load(api)
    kbs = api.client.get("/v1/knowledge-bases", headers=api.reader).json()
    assert [(k["slug"], k["document_count"]) for k in kbs] == [("trocas", 1)]

    found = api.client.post(
        "/v1/knowledge-bases/trocas/search",
        json={"query": "prazo para trocar o produto", "filters": {"area": "pos-venda"}},
        headers=api.reader,
    ).json()
    assert "sete dias" in found["results"][0]["text"]

    answer = api.client.post(
        "/v1/knowledge-bases/trocas/query",
        json={"question": "Qual o prazo para trocar o produto?"},
        headers=api.reader,
    ).json()
    assert answer["grounded"] is True
    assert answer["citations"][0]["document_id"] == doc_id

    doc = api.client.get(
        f"/v1/knowledge-bases/trocas/documents/{doc_id}?include_text=true", headers=api.reader
    ).json()
    assert doc["text"].startswith("# Política de Trocas")
    assert doc["metadata"] == {"area": "pos-venda"}


def test_query_stream(api: Api) -> None:
    _load(api)
    with api.client.stream(
        "POST",
        "/v1/knowledge-bases/trocas/query",
        json={"question": "condições da troca", "stream": True},
        headers=api.reader,
    ) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = r.read().decode()
    events = [
        (block.split("\n")[0][7:], json.loads(block.split("\n")[1][6:]))
        for block in body.strip().split("\n\n")
    ]
    names = [name for name, _ in events]
    assert names[-2:] == ["citations", "done"]
    assert "delta" in names
    assert events[-1][1]["grounded"] is True


def test_delete_requires_confirmation_and_admin(api: Api) -> None:
    doc_id = _load(api)
    url = f"/v1/knowledge-bases/trocas/documents/{doc_id}"
    assert api.client.delete(f"{url}?confirm=true", headers=api.reader).status_code == 403
    preview = api.client.delete(url, headers=api.admin).json()
    assert preview["executed"] is False and preview["will_delete"]["chunks"] >= 1
    assert api.client.delete(f"{url}?confirm=true", headers=api.admin).json()["executed"]
    assert api.client.get(url, headers=api.reader).status_code == 404


def test_tenant_isolation_over_http(api: Api) -> None:
    doc_id = _load(api)
    other = api.other
    assert api.client.get("/v1/knowledge-bases", headers=other).json() == []
    assert api.client.get("/v1/knowledge-bases/trocas", headers=other).status_code == 404
    r = api.client.post("/v1/knowledge-bases/trocas/search", json={"query": "prazo"}, headers=other)
    assert r.status_code == 404
    api.client.post(
        "/v1/knowledge-bases",
        json={"slug": "trocas", "name": "Globex", "config": KB_CONFIG},
        headers=other,
    )
    url = f"/v1/knowledge-bases/trocas/documents/{doc_id}"
    assert api.client.get(url, headers=other).status_code == 404
    assert api.client.delete(f"{url}?confirm=true", headers=other).status_code == 404
    results = api.client.post(
        "/v1/knowledge-bases/trocas/search", json={"query": "prazo"}, headers=other
    ).json()["results"]
    assert results == []


def test_validation_errors(api: Api) -> None:
    _load(api)
    r = api.client.post(
        "/v1/knowledge-bases/trocas/search", json={"query": "x", "top_k": 999}, headers=api.reader
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_argument"
    r = api.client.post(
        "/v1/knowledge-bases/trocas/documents",
        files={"file": ("x.pdf", b"not a pdf", "application/pdf")},
        headers=api.admin,
    )
    assert r.status_code == 422
    r = api.client.post(
        "/v1/knowledge-bases/trocas/documents",
        files={"file": ("x.txt", b"ok", "text/plain")},
        headers=api.reader,
    )
    assert r.status_code == 403
