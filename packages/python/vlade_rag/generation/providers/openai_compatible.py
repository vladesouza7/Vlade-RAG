"""Adapters for any OpenAI-compatible API (OpenAI, OpenRouter, vLLM, LM Studio, and others)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from vlade_rag.core.domain import (
    Generation,
    GenerationDelta,
    GenerationParams,
    InvalidArgument,
    Message,
    TokenUsage,
)
from vlade_rag.integrations.external.http import ProviderHttpClient, parse_sse_data


class OpenAICompatibleEmbeddingProvider:
    max_batch_size = 256

    def __init__(
        self,
        http: ProviderHttpClient,
        provider: str,
        model: str,
        dimension: int,
        *,
        send_dimensions: bool = False,
    ) -> None:
        self.http = http
        self.provider = provider
        self.model = model
        self.dimension = dimension
        self.send_dimensions = send_dimensions

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, Any] = {"model": self.model, "input": list(texts)}
        if self.send_dimensions:
            payload["dimensions"] = self.dimension
        data = await self.http.post_json("/embeddings", payload)
        items = sorted(data.get("data", []), key=lambda d: int(d.get("index", 0)))
        vectors = [[float(x) for x in item["embedding"]] for item in items]
        if len(vectors) != len(texts):
            raise InvalidArgument(f"{self.provider} returned a different number of embeddings.")
        if any(len(v) != self.dimension for v in vectors):
            raise InvalidArgument(
                f"Model '{self.model}' returned vectors with a dimension different from "
                f"{self.dimension}."
            )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


class OpenAICompatibleLLM:
    def __init__(self, http: ProviderHttpClient, name: str) -> None:
        self.http = http
        self.name = name

    @staticmethod
    def _payload(
        messages: Sequence[Message], params: GenerationParams, stream: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": params.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": params.temperature,
            "max_tokens": params.max_output_tokens,
            "stream": stream,
        }
        if params.stop:
            payload["stop"] = list(params.stop)
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    @staticmethod
    def _usage(data: dict[str, Any]) -> TokenUsage | None:
        usage = data.get("usage")
        if not usage:
            return None
        return TokenUsage(
            int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        )

    async def generate(self, messages: Sequence[Message], params: GenerationParams) -> Generation:
        data = await self.http.post_json(
            "/chat/completions", self._payload(messages, params, False)
        )
        choice = (data.get("choices") or [{}])[0]
        return Generation(
            text=str((choice.get("message") or {}).get("content") or ""),
            model=str(data.get("model", params.model)),
            usage=self._usage(data) or TokenUsage(),
            finish_reason=choice.get("finish_reason"),
        )

    async def stream(
        self, messages: Sequence[Message], params: GenerationParams
    ) -> AsyncIterator[GenerationDelta]:
        payload = self._payload(messages, params, True)
        async with self.http.stream_lines("/chat/completions", payload) as lines:
            async for line in lines:
                data = parse_sse_data(line)
                if data is None:
                    continue
                usage = self._usage(data)
                for choice in data.get("choices") or []:
                    text = (choice.get("delta") or {}).get("content") or ""
                    if text:
                        yield GenerationDelta(text=str(text))
                if usage is not None:
                    yield GenerationDelta(text="", usage=usage)
