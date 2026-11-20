"""The API reranker (roadmap 3.1, ADR-0018). No network: a fake HTTP client."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from vlade_rag.bootstrap import build_runtime
from vlade_rag.core.config import Settings
from vlade_rag.core.domain import Chunk, InvalidArgument, ProviderUnavailable, ScoredChunk
from vlade_rag.core.domain.kb_config import RerankConfig
from vlade_rag.core.ports import Reranker
from vlade_rag.reranking.api import ApiReranker

pytestmark = pytest.mark.anyio


class FakeHttp:
    """Records each request and answers with ``response``."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post_json(self, path: str, payload: dict[str, Any]) -> Any:
        self.calls.append((path, payload))
        return self.response


def candidates(*texts: str) -> list[ScoredChunk]:
    tenant, kb, doc, version = uuid4(), uuid4(), uuid4(), uuid4()
    return [
        ScoredChunk(
            Chunk(uuid4(), tenant, kb, doc, version, i, text, 5, 0, len(text)),
            score=1.0 / (i + 1),
            rank=i + 1,
            retriever="fusion",
        )
        for i, text in enumerate(texts)
    ]


def reranker(response: Any) -> tuple[ApiReranker, FakeHttp]:
    http = FakeHttp(response)
    return ApiReranker(http, "openrouter", "cohere/rerank-v3.5"), http  # type: ignore[arg-type]


async def test_orders_the_candidates_by_relevance() -> None:
    items = candidates("a", "b", "c")
    api, http = reranker(
        {
            "results": [
                {"index": 2, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.4},
                {"index": 1, "relevance_score": 0.1},
            ]
        }
    )
    out = await api.rerank("pergunta", items, 3)

    assert [c.chunk.text for c in out] == ["c", "a", "b"]
    assert [c.rank for c in out] == [1, 2, 3]
    assert [c.score for c in out] == [0.9, 0.4, 0.1]
    assert {c.retriever for c in out} == {"rerank"}
    assert isinstance(api, Reranker)
    path, payload = http.calls[0]
    assert path == "/rerank"
    assert payload == {
        "model": "cohere/rerank-v3.5",
        "query": "pergunta",
        "documents": ["a", "b", "c"],
        "top_n": 3,
    }


async def test_does_not_trust_the_order_of_the_response() -> None:
    api, _ = reranker(
        {"results": [{"index": 0, "relevance_score": 0.2}, {"index": 1, "relevance_score": 0.8}]}
    )
    out = await api.rerank("q", candidates("a", "b"), 2)
    assert [c.chunk.text for c in out] == ["b", "a"]


async def test_equal_scores_keep_the_order_of_the_candidates() -> None:
    api, _ = reranker(
        {"results": [{"index": 1, "relevance_score": 0.5}, {"index": 0, "relevance_score": 0.5}]}
    )
    out = await api.rerank("q", candidates("a", "b"), 2)
    assert [c.chunk.text for c in out] == ["a", "b"]


async def test_top_n_is_capped_at_the_number_of_candidates_and_applied() -> None:
    api, http = reranker(
        {"results": [{"index": 1, "relevance_score": 0.8}, {"index": 0, "relevance_score": 0.2}]}
    )
    out = await api.rerank("q", candidates("a", "b"), 50)
    assert http.calls[0][1]["top_n"] == 2 and len(out) == 2

    api, _ = reranker(
        {"results": [{"index": 1, "relevance_score": 0.8}, {"index": 0, "relevance_score": 0.2}]}
    )
    assert len(await api.rerank("q", candidates("a", "b"), 1)) == 1  # the provider ignored top_n


async def test_a_duplicate_index_counts_once() -> None:
    api, _ = reranker(
        {"results": [{"index": 0, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]}
    )
    out = await api.rerank("q", candidates("a", "b"), 2)
    assert [c.chunk.text for c in out] == ["a"]


async def test_no_candidates_makes_no_request() -> None:
    api, http = reranker({"results": []})
    assert await api.rerank("q", [], 5) == []
    assert http.calls == []


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"results": []},
        {"results": "x"},
        [],
        {"results": [{"index": 5, "relevance_score": 0.1}]},
        {"results": [{"index": -1, "relevance_score": 0.1}]},
    ],
)
async def test_a_malformed_response_is_a_provider_error(response: Any) -> None:
    api, _ = reranker(response)
    with pytest.raises(ProviderUnavailable):
        await api.rerank("q", candidates("a", "b"), 2)


async def test_top_n_below_one_is_refused() -> None:
    api, _ = reranker({"results": []})
    with pytest.raises(InvalidArgument):
        await api.rerank("q", candidates("a"), 0)


async def test_openrouter_resolves_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLADE_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_OBJECT_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_PROVIDERS__OPENROUTER__API_KEY", "sk-or")
    monkeypatch.setenv("VLADE_PROVIDERS__COMPATIBLE__JINA__BASE_URL", "https://api.jina.ai/v1")
    monkeypatch.setenv("VLADE_PROVIDERS__COMPATIBLE__JINA__API_KEY", "jina-key")
    runtime = await build_runtime(Settings(), load_plugins=False)
    try:
        resolve = runtime.deps.rerankers
        assert resolve is not None
        api = resolve(RerankConfig(provider="openrouter", model="cohere/rerank-4-fast"))
        assert api.model == "cohere/rerank-4-fast"  # type: ignore[attr-defined]
        client = api.http.client  # type: ignore[attr-defined]
        assert str(client.base_url).rstrip("/") == "https://openrouter.ai/api/v1"
        assert client.headers["authorization"] == "Bearer sk-or"
        # A provider the user adds gets the same adapter.
        jina = resolve(RerankConfig(provider="jina", model="jina-reranker"))
        assert str(jina.http.client.base_url).rstrip("/") == "https://api.jina.ai/v1"  # type: ignore[attr-defined]
        # Providers without a rerank endpoint, and the local adapter (not built yet), are refused.
        for name in ("openai", "gemini", "opencode", "sentence-transformers"):
            with pytest.raises(InvalidArgument, match=f"Unknown reranker adapter '{name}'"):
                resolve(RerankConfig(provider=name, model="m"))
    finally:
        await runtime.aclose()
