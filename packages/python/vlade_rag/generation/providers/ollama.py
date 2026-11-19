"""Ollama adapters: embeddings (``/api/embed``) and chat (``/api/chat``)."""

from __future__ import annotations

import json
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
from vlade_rag.integrations.external.http import ProviderHttpClient


class OllamaEmbeddingProvider:
    provider = "ollama"
    max_batch_size = 64

    def __init__(self, http: ProviderHttpClient, model: str, dimension: int) -> None:
        self.http = http
        self.model = model
        self.dimension = dimension

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        data = await self.http.post_json("/api/embed", {"model": self.model, "input": list(texts)})
        vectors: list[list[float]] = [[float(x) for x in v] for v in data.get("embeddings", [])]
        if len(vectors) != len(texts):
            raise InvalidArgument("Ollama returned a different number of embeddings.")
        for vector in vectors:
            if len(vector) != self.dimension:
                raise InvalidArgument(
                    f"Model '{self.model}' returned {len(vector)} dimensions; the knowledge base "
                    f"expects {self.dimension}."
                )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


class OllamaLLM:
    name = "ollama"

    def __init__(self, http: ProviderHttpClient, think: bool | None = None) -> None:
        self.http = http
        self.think = think

    def _payload(
        self, messages: Sequence[Message], params: GenerationParams, stream: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": params.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "options": {
                "temperature": params.temperature,
                "num_predict": params.max_output_tokens,
            },
        }
        if params.stop:
            payload["options"]["stop"] = list(params.stop)
        if self.think is not None:
            payload["think"] = self.think
        return payload

    @staticmethod
    def _usage(data: dict[str, Any]) -> TokenUsage:
        return TokenUsage(int(data.get("prompt_eval_count", 0)), int(data.get("eval_count", 0)))

    async def generate(self, messages: Sequence[Message], params: GenerationParams) -> Generation:
        data = await self.http.post_json("/api/chat", self._payload(messages, params, False))
        return Generation(
            text=str(data.get("message", {}).get("content", "")),
            model=str(data.get("model", params.model)),
            usage=self._usage(data),
            finish_reason=data.get("done_reason"),
        )

    async def stream(
        self, messages: Sequence[Message], params: GenerationParams
    ) -> AsyncIterator[GenerationDelta]:
        async with self.http.stream_lines(
            "/api/chat", self._payload(messages, params, True)
        ) as lines:
            async for line in lines:
                if not line.strip():
                    continue
                data = json.loads(line)
                text = str(data.get("message", {}).get("content", ""))
                if data.get("done"):
                    yield GenerationDelta(text=text, usage=self._usage(data))
                    return
                if text:
                    yield GenerationDelta(text=text)
