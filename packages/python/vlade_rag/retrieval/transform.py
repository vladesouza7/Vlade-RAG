"""Query transformers: rewrite, multi-query and HyDE (RF-25, ADR-0019).

Each transformer asks the LLM of the knowledge base for a new search text and returns the
original query first, then the derived queries. The search runs every query and fuses the lists
with RRF. If the LLM fails or answers with nothing usable, the transformer returns only the
original query: a search must not fail because the rewrite failed.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import replace
from typing import Literal

from vlade_rag.core.domain import (
    GenerationParams,
    InvalidArgument,
    KnowledgeBase,
    Message,
    ProviderUnavailable,
    Query,
    TenantContext,
)
from vlade_rag.core.domain.kb_config import GenerationConfig
from vlade_rag.core.ports import LLMProvider, PromptRegistry
from vlade_rag.generation.prompts import QUERY_HYDE, QUERY_MULTI, QUERY_REWRITE

log = logging.getLogger(__name__)

Mode = Literal["rewrite", "multi_query", "hyde"]

PROMPT: dict[Mode, str] = {"rewrite": QUERY_REWRITE, "multi_query": QUERY_MULTI, "hyde": QUERY_HYDE}
MAX_VARIANTS = 3
MAX_HYDE_CHARS = 1000
_BULLET = re.compile(r"^\s*(?:[-*•]+|\d+[.)])\s*")


class LLMQueryTransformer:
    def __init__(
        self,
        mode: Mode,
        llms: Callable[[GenerationConfig], LLMProvider],
        prompts: PromptRegistry,
        *,
        max_query_chars: int = 2000,
    ) -> None:
        if mode not in PROMPT:
            raise InvalidArgument(f"Unknown query transform '{mode}'.")
        self.name: str = mode
        self.mode: Mode = mode
        self.llms = llms
        self.prompts = prompts
        self.max_query_chars = max_query_chars

    async def transform(self, ctx: TenantContext, kb: KnowledgeBase, query: Query) -> list[Query]:
        gen = kb.config.generation
        language = query.language or kb.language
        template = await self.prompts.get(PROMPT[self.mode], language)
        messages = [
            Message("system", template.system),
            Message("user", template.render_user(question=query.text)),
        ]
        # The limit of the base, not a smaller one of our own: a reasoning model spends part of the
        # limit on its thinking and can end with no answer at all (finish_reason "length").
        params = GenerationParams(
            model=gen.model, temperature=0.0, max_output_tokens=gen.max_output_tokens
        )
        try:
            result = await self.llms(gen).generate(messages, params)
        except ProviderUnavailable as exc:
            log.warning("query transform '%s' failed; using the original query: %s", self.name, exc)
            return [query]
        texts = self._parse(result.text, query.text)
        if not texts:
            log.warning(
                "query transform '%s' returned no usable text (finish_reason=%s)",
                self.name,
                result.finish_reason,
            )
            return [query]
        # HyDE: the hypothetical answer is a document, so only the dense retriever reads it.
        # Its OR-of-terms lexical form would match almost every chunk.
        only = ("dense",) if self.mode == "hyde" else None
        return [query, *(replace(query, text=text, retrievers=only) for text in texts)]

    def _parse(self, raw: str, original: str) -> list[str]:
        lines = [_BULLET.sub("", line).strip().strip("\"'“”") for line in raw.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return []
        if self.mode == "hyde":
            texts = [" ".join(lines)[:MAX_HYDE_CHARS]]
        elif self.mode == "rewrite":
            texts = lines[:1]
        else:
            texts = lines[:MAX_VARIANTS]
        seen = {original.casefold()}
        unique = []
        for text in texts:
            text = text[: self.max_query_chars]
            if text.casefold() not in seen:
                seen.add(text.casefold())
                unique.append(text)
        return unique
