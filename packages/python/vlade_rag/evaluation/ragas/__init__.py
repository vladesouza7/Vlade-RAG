"""Answer metrics with RAGAS (RF-71, roadmap 3.7, ADR-0025). Install the extra ``eval``.

``RagasScorer`` calls a judge LLM and an embedding model through an OpenAI-compatible API, for
example OpenRouter. Every call costs money: see ``evals/reports`` for the size of a run.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping, Sequence
from typing import Any

from vlade_rag.core.domain import InvalidArgument

METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")


class RagasScorer:
    """The four RAGAS metrics of RF-71.

    - ``faithfulness``: share of the claims of the answer that the context supports.
    - ``answer_relevancy``: how well the answer addresses the question (needs embeddings).
    - ``context_precision``: whether the useful chunks come first (needs the reference answer).
    - ``context_recall``: share of the reference answer that the context covers (needs it too).

    A metric that fails or returns NaN is ``None``. A refusal ("not found") without context
    has no claims, so its faithfulness is ``None``.
    """

    name = "ragas"
    metrics: tuple[str, ...] = METRICS

    def __init__(
        self,
        *,
        judge_model: str,
        embeddings_model: str,
        base_url: str,
        api_key: str,
        timeout: float = 120.0,
        max_retries: int = 3,
        max_tokens: int = 8192,
        reasoning: bool = False,
    ) -> None:
        """``max_tokens`` limits each judge answer. Faithfulness lists every claim of the answer,
        and the RAGAS default (1024) cuts a long list. ``reasoning=False`` asks OpenRouter to turn
        off the reasoning of the judge: its tokens count in ``max_tokens``, and a long context made
        the judge stop before the answer. Other providers get no extra field."""
        try:
            from openai import AsyncOpenAI
            from ragas import __version__ as ragas_version
            from ragas.embeddings.base import embedding_factory
            from ragas.llms import llm_factory
            from ragas.metrics.collections import (
                AnswerRelevancy,
                ContextPrecisionWithReference,
                ContextRecall,
                Faithfulness,
            )
        except ImportError as exc:  # pragma: no cover - depends on the installed extras
            raise InvalidArgument(
                "RAGAS is not installed. Install the extra 'eval': pip install 'vlade-rag[eval]'."
            ) from exc
        client = AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        extra: dict[str, Any] = {}
        if not reasoning and "openrouter.ai" in base_url:
            extra["extra_body"] = {"reasoning": {"enabled": False}}
        llm = llm_factory(
            judge_model, provider="openai", client=client, max_tokens=max_tokens, **extra
        )
        embeddings = embedding_factory(
            "openai", model=embeddings_model, client=client, interface="modern"
        )
        self.judge_model = judge_model
        self.max_tokens = max_tokens
        self.reasoning = reasoning
        self.embeddings_model = embeddings_model
        self.base_url = base_url
        self.ragas_version = ragas_version
        self._faithfulness = Faithfulness(llm=llm)
        # interface="modern" returns a BaseRagasEmbedding, the type AnswerRelevancy needs.
        self._answer_relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings)  # type: ignore[arg-type]
        self._context_precision = ContextPrecisionWithReference(llm=llm)
        self._context_recall = ContextRecall(llm=llm)
        self.errors: dict[str, int] = {}

    def describe(self) -> Mapping[str, object]:
        return {
            "ragas_version": self.ragas_version,
            "judge_model": self.judge_model,
            "judge_max_tokens": self.max_tokens,
            "judge_reasoning": self.reasoning,
            "embeddings_model": self.embeddings_model,
            "base_url": self.base_url,
            "metrics": list(self.metrics),
            "errors": dict(self.errors),
        }

    async def score(
        self, question: str, answer: str, contexts: Sequence[str], reference: str | None
    ) -> Mapping[str, float | None]:
        calls: dict[str, Any] = {
            "answer_relevancy": self._answer_relevancy.ascore(user_input=question, response=answer),
        }
        if contexts:
            calls["faithfulness"] = self._faithfulness.ascore(
                user_input=question, response=answer, retrieved_contexts=list(contexts)
            )
            if reference:
                calls["context_precision"] = self._context_precision.ascore(
                    user_input=question, reference=reference, retrieved_contexts=list(contexts)
                )
                calls["context_recall"] = self._context_recall.ascore(
                    user_input=question, retrieved_contexts=list(contexts), reference=reference
                )
        names = list(calls)
        results = await asyncio.gather(*calls.values(), return_exceptions=True)
        scores: dict[str, float | None] = dict.fromkeys(self.metrics)
        for name, result in zip(names, results, strict=True):
            if isinstance(result, BaseException):
                key = f"{name}: {type(result).__name__}"
                self.errors[key] = self.errors.get(key, 0) + 1
                continue
            value = getattr(result, "value", result)
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            scores[name] = None if math.isnan(number) else number
        return scores
