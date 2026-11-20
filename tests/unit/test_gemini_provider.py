"""Gemini through its OpenAI-compatible endpoint (roadmap 2.6). No network: a fake HTTP client."""

from __future__ import annotations

from typing import Any

import pytest

from vlade_rag.bootstrap import build_runtime
from vlade_rag.core.config import Settings
from vlade_rag.core.domain import InvalidArgument
from vlade_rag.core.domain.kb_config import EmbeddingsConfig, GenerationConfig
from vlade_rag.generation.providers.openai_compatible import OpenAICompatibleEmbeddingProvider

pytestmark = pytest.mark.anyio

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


class FakeHttp:
    """Records the payload of each request and answers with vectors of ``dimension``."""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, payload))
        return {
            "data": [
                {"index": i, "embedding": [0.0] * self.dimension}
                for i, _ in enumerate(payload["input"])
            ]
        }


def test_gemini_is_a_built_in_compatible_provider() -> None:
    providers = Settings().providers
    assert providers.gemini.base_url == GEMINI_URL
    assert providers.gemini.embedding_dimensions is False
    assert providers.openai_compatible()["gemini"] is providers.gemini


async def test_gemini_resolves_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLADE_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_OBJECT_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_PROVIDERS__GEMINI__API_KEY", "gm-key")
    runtime = await build_runtime(Settings(), load_plugins=False)
    try:
        llm = runtime.deps.llms(GenerationConfig(provider="gemini", model="any-model"))
        client = llm.http.client  # type: ignore[attr-defined]
        assert str(client.base_url).rstrip("/") == GEMINI_URL
        assert client.headers["authorization"] == "Bearer gm-key"
        embedder = runtime.deps.embeddings(
            EmbeddingsConfig(provider="gemini", model="any-embedding", dimension=768)
        )
        assert embedder.provider == "gemini" and embedder.dimension == 768
        assert embedder.send_dimensions is False  # type: ignore[attr-defined]
        with pytest.raises(InvalidArgument, match="Unknown llm adapter 'gemin'"):
            runtime.deps.llms(GenerationConfig(provider="gemin", model="m"))
    finally:
        await runtime.aclose()


async def test_embedding_dimensions_are_sent_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VLADE_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_OBJECT_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_PROVIDERS__GEMINI__EMBEDDING_DIMENSIONS", "true")
    runtime = await build_runtime(Settings(), load_plugins=False)
    try:
        embedder = runtime.deps.embeddings(
            EmbeddingsConfig(provider="gemini", model="any-embedding", dimension=768)
        )
        assert embedder.send_dimensions is True  # type: ignore[attr-defined]
        # The other providers keep the default: nothing changes for them.
        other = runtime.deps.embeddings(
            EmbeddingsConfig(provider="openrouter", model="m", dimension=1536)
        )
        assert other.send_dimensions is False  # type: ignore[attr-defined]
    finally:
        await runtime.aclose()


@pytest.mark.parametrize(("flag", "expected"), [(False, None), (True, 768)])
async def test_payload_has_dimensions_only_with_the_flag(flag: bool, expected: int | None) -> None:
    http = FakeHttp(dimension=768)
    embedder = OpenAICompatibleEmbeddingProvider(
        http,  # type: ignore[arg-type]
        "gemini",
        "any-embedding",
        768,
        send_dimensions=flag,
    )
    vectors = await embedder.embed_documents(["um", "dois"])
    assert [len(v) for v in vectors] == [768, 768]
    path, payload = http.calls[0]
    assert path == "/embeddings"
    assert payload["model"] == "any-embedding" and payload["input"] == ["um", "dois"]
    assert payload.get("dimensions") == expected


async def test_a_vector_of_the_wrong_dimension_is_refused() -> None:
    embedder = OpenAICompatibleEmbeddingProvider(
        FakeHttp(dimension=3072),  # type: ignore[arg-type]
        "gemini",
        "any-embedding",
        1536,
    )
    with pytest.raises(InvalidArgument, match="dimension different from 1536"):
        await embedder.embed_query("texto")
