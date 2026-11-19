"""Provider adapters against a mocked HTTP transport."""

from __future__ import annotations

import json

import httpx2
import pytest

from vlade_rag.core.domain import (
    GenerationParams,
    InvalidArgument,
    Message,
    ProviderUnavailable,
    TokenUsage,
)
from vlade_rag.generation.providers.ollama import OllamaEmbeddingProvider, OllamaLLM
from vlade_rag.generation.providers.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleLLM,
)
from vlade_rag.integrations.external.http import ProviderHttpClient

pytestmark = pytest.mark.anyio
MESSAGES = [Message("system", "s"), Message("user", "u")]
PARAMS = GenerationParams(model="m", temperature=0.2, max_output_tokens=50)


def client(handler: object, retries: int = 2) -> ProviderHttpClient:
    return ProviderHttpClient(
        "test",
        "http://provider",
        retries=retries,
        backoff=0,
        transport=httpx2.MockTransport(handler),  # type: ignore[arg-type]
    )


async def test_ollama_embeddings() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        assert request.url.path == "/api/embed"
        return httpx2.Response(200, json={"embeddings": [[0.1, 0.2]] * len(body["input"])})

    provider = OllamaEmbeddingProvider(client(handler), "bge-m3", 2)
    assert await provider.embed_documents(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert await provider.embed_query("a") == [0.1, 0.2]


async def test_ollama_wrong_dimension() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    with pytest.raises(InvalidArgument, match="dimensions"):
        await OllamaEmbeddingProvider(client(handler), "bge-m3", 2).embed_query("a")


async def test_ollama_chat_and_stream() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        assert body["options"] == {"temperature": 0.2, "num_predict": 50}
        assert body["think"] is False
        if not body["stream"]:
            return httpx2.Response(
                200,
                json={
                    "model": "m",
                    "message": {"content": "olá [1]"},
                    "prompt_eval_count": 10,
                    "eval_count": 3,
                    "done_reason": "stop",
                },
            )
        lines = [
            {"message": {"content": "ol"}, "done": False},
            {"message": {"content": "á"}, "done": False},
            {"message": {"content": ""}, "done": True, "prompt_eval_count": 10, "eval_count": 2},
        ]
        return httpx2.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())

    llm = OllamaLLM(client(handler), think=False)
    generation = await llm.generate(MESSAGES, PARAMS)
    assert (generation.text, generation.usage) == ("olá [1]", TokenUsage(10, 3))
    deltas = [d async for d in llm.stream(MESSAGES, PARAMS)]
    assert "".join(d.text for d in deltas) == "olá"
    assert deltas[-1].usage == TokenUsage(10, 2)


async def test_openai_compatible_embeddings_sorted_by_index() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/embeddings"
        return httpx2.Response(
            200,
            json={"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]},
        )

    provider = OpenAICompatibleEmbeddingProvider(client(handler), "openai", "e", 1)
    assert await provider.embed_documents(["a", "b"]) == [[1.0], [2.0]]


async def test_openai_compatible_chat_stream() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if not body["stream"]:
            return httpx2.Response(
                200,
                json={
                    "model": "m",
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 1},
                },
            )
        assert body["stream_options"] == {"include_usage": True}
        events = [
            {"choices": [{"delta": {"content": "o"}}]},
            {"choices": [{"delta": {"content": "k"}}]},
            {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
        ]
        sse = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
        return httpx2.Response(200, content=sse.encode())

    llm = OpenAICompatibleLLM(client(handler), "openai")
    generation = await llm.generate(MESSAGES, PARAMS)
    assert (generation.text, generation.usage) == ("ok", TokenUsage(5, 1))
    deltas = [d async for d in llm.stream(MESSAGES, PARAMS)]
    assert "".join(d.text for d in deltas) == "ok"
    assert deltas[-1].usage == TokenUsage(5, 2)


async def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx2.Response(503, text="busy")
        return httpx2.Response(200, json={"embeddings": [[1.0]]})

    provider = OllamaEmbeddingProvider(client(handler, retries=2), "m", 1)
    assert await provider.embed_query("a") == [1.0]
    assert calls["n"] == 3


async def test_gives_up_with_provider_unavailable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    with pytest.raises(ProviderUnavailable):
        await OllamaEmbeddingProvider(client(handler, retries=1), "m", 1).embed_query("a")


async def test_client_error_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        return httpx2.Response(404, text="model not found")

    with pytest.raises(InvalidArgument, match="404"):
        await OllamaLLM(client(handler)).generate(MESSAGES, PARAMS)
    assert calls["n"] == 1
