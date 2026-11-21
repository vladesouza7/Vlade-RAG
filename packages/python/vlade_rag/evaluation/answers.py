"""Answer evaluation: runs each question through the query flow and scores the answer (RF-71).

The evaluator runs the engine of the base (``AnswerQuery`` steps, ADR-0023), so it scores the
same answer and the same context that a user gets. A scorer (``AnswerScorer``) gives the metrics.
``vlade_rag.evaluation.ragas.RagasScorer`` scores with RAGAS (extra ``eval``, ADR-0025).
The report records the whole configuration of the run (RF-72).
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol

from vlade_rag import __version__
from vlade_rag.core.application import Dependencies
from vlade_rag.core.application.answer import AnswerQuery, Draft, PreparedQuery
from vlade_rag.core.domain import InvalidArgument, KnowledgeBase, Query, Role, TenantContext
from vlade_rag.core.domain.kb_config import QueryTransform, RerankConfig, RetrieverName
from vlade_rag.core.ports import EvalItem, EvalReport


class AnswerScorer(Protocol):
    """Scores one answer. A metric that cannot be scored is ``None``."""

    name: str
    metrics: tuple[str, ...]

    def describe(self) -> Mapping[str, object]:
        """The models and settings of the scorer, for the report (RF-72)."""
        ...

    async def score(
        self, question: str, answer: str, contexts: Sequence[str], reference: str | None
    ) -> Mapping[str, float | None]: ...


class AnswerEvaluator:
    name = "answers"

    def __init__(
        self,
        deps: Dependencies,
        scorer: AnswerScorer,
        *,
        rerank: RerankConfig | None = None,
        retrievers: Sequence[RetrieverName] | None = None,
        query_transform: QueryTransform | None = None,
        concurrency: int = 4,
    ) -> None:
        """``rerank``, ``retrievers`` and ``query_transform`` replace the same settings of the
        base for this run. The base is not changed."""
        if concurrency < 1:
            raise InvalidArgument("concurrency must be 1 or more.")
        self.deps = deps
        self.scorer = scorer
        self.rerank = rerank
        self.retrievers = tuple(retrievers) if retrievers else None
        self.query_transform = query_transform
        self.concurrency = concurrency

    async def evaluate(
        self, ctx: TenantContext, kb: KnowledgeBase, items: Sequence[EvalItem]
    ) -> EvalReport:
        ctx.require(Role.ADMIN)
        if not items:
            raise InvalidArgument("The dataset has no question.")
        kb = self._with_overrides(kb)
        steps = AnswerQuery(self.deps)
        engine = steps.engine(kb)
        language = kb.config.language
        template = await self.deps.prompts.get(kb.config.generation.prompt, language)
        top_k = steps.search.validate_top_k(kb.config.retrieval.rerank.top_n)
        semaphore = asyncio.Semaphore(self.concurrency)

        async def one(item: EvalItem) -> dict[str, Any]:
            async with semaphore:
                started = time.perf_counter()
                query = Query(steps.search.validate_text(item.question), kb.id, None, language)
                prepared = PreparedQuery(kb, query, top_k, template, started)
                draft: Draft | None = None
                async for event in engine.run(steps, ctx, prepared, False):
                    if isinstance(event, Draft):
                        draft = event
                if draft is None:  # pragma: no cover - an engine always ends with a Draft
                    raise RuntimeError("The query engine ended without an answer.")
                answer = draft.validated.text
                contexts = [c.chunk.text for c in draft.context]
                scores = await self.scorer.score(
                    item.question, answer, contexts, item.expected_answer
                )
                return {
                    "question": item.question,
                    "expected_answer": item.expected_answer,
                    "answer": answer,
                    "grounded": draft.validated.grounded,
                    "cited_documents": [c.document_title for c in draft.validated.citations],
                    "context_documents": [c.chunk.document_title for c in draft.context],
                    "scores": dict(scores),
                    "seconds": round(time.perf_counter() - started, 3),
                }

        details = await asyncio.gather(*(one(item) for item in items))
        metrics: dict[str, float] = {}
        scored: dict[str, int] = {}
        for name in self.scorer.metrics:
            values = [
                v for d in details if (v := d["scores"].get(name)) is not None and not math.isnan(v)
            ]
            scored[name] = len(values)
            if values:
                metrics[name] = round(sum(values) / len(values), 6)
        metrics["grounded_rate"] = round(sum(d["grounded"] for d in details) / len(details), 6)
        return EvalReport(
            metrics=metrics,
            config=self._config(kb, len(items), scored),
            items=len(items),
            details=tuple(details),
        )

    def _with_overrides(self, kb: KnowledgeBase) -> KnowledgeBase:
        retrieval = kb.config.retrieval
        updates: dict[str, Any] = {}
        if self.retrievers is not None:
            updates["retrievers"] = self.retrievers
        if self.query_transform is not None:
            updates["query_transform"] = self.query_transform
        if self.rerank is not None:
            updates["rerank"] = self.rerank
        if not updates:
            return kb
        retrieval = retrieval.model_copy(update=updates)
        return replace(kb, config=kb.config.model_copy(update={"retrieval": retrieval}))

    def _config(
        self, kb: KnowledgeBase, total: int, scored: Mapping[str, int]
    ) -> Mapping[str, object]:
        return {
            "evaluator": self.name,
            "vlade_rag_version": __version__,
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "knowledge_base": {"slug": kb.slug, "id": str(kb.id), "epoch": kb.epoch},
            "knowledge_base_config": kb.config.model_dump(mode="json"),
            "scorer": {"name": self.scorer.name, **dict(self.scorer.describe())},
            "questions": {"in_dataset": total, "scored_per_metric": dict(scored)},
        }
