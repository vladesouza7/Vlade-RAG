"""Offline LLM provider that answers with the first sentence of the first sources.

It reads the ``<source>`` blocks of the prompt and returns sentences with ``[n]`` citations.
Use it for tests, CI and demos without a model. It does not reason.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence

from vlade_rag.core.domain import (
    Generation,
    GenerationDelta,
    GenerationParams,
    Message,
    TokenUsage,
)
from vlade_rag.native import count_tokens

_SOURCE = re.compile(r'<source id="(\d+)"[^>]*>\n(.*?)\n</source>', re.DOTALL)
_SENTENCE = re.compile(r"(.+?[.!?…])(\s|$)", re.DOTALL)


class ExtractiveLLM:
    name = "extractive"

    def __init__(self, max_sources: int = 2, not_found: str = "") -> None:
        self.max_sources = max_sources
        self.not_found = not_found

    def _answer(self, messages: Sequence[Message]) -> str:
        prompt = "\n".join(m.content for m in messages if m.role == "user")
        sentences = []
        for number, text in _SOURCE.findall(prompt)[: self.max_sources]:
            flat = " ".join(text.split())
            match = _SENTENCE.match(flat)
            sentence = (match.group(1) if match else flat[:300]).strip()
            if sentence:
                sentences.append(f"{sentence} [{number}]")
        return " ".join(sentences) or self.not_found

    async def generate(self, messages: Sequence[Message], params: GenerationParams) -> Generation:
        text = self._answer(messages)
        usage = TokenUsage(
            input_tokens=sum(count_tokens([m.content for m in messages])),
            output_tokens=count_tokens([text])[0],
        )
        return Generation(text=text, model=self.name, usage=usage, finish_reason="stop")

    async def stream(
        self, messages: Sequence[Message], params: GenerationParams
    ) -> AsyncIterator[GenerationDelta]:
        generation = await self.generate(messages, params)
        words = generation.text.split(" ")
        for i, word in enumerate(words):
            last = i == len(words) - 1
            yield GenerationDelta(
                text=word if last else word + " ", usage=generation.usage if last else None
            )
