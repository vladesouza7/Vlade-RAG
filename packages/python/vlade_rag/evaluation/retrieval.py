"""Retrieval evaluation: runs each question through ``Search`` and scores the ranking (RF-70).

The score is per document. The evaluator fetches up to ``FETCH_FACTOR`` chunks for each position
it needs, groups the chunks by document and ranks each document at the position of its best
chunk. The report records the whole configuration of the run (RF-72).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from vlade_rag import __version__
from vlade_rag.core.application import Dependencies, Search
from vlade_rag.core.domain import InvalidArgument, KnowledgeBase, Query, Role, TenantContext
from vlade_rag.core.domain.kb_config import RerankConfig
from vlade_rag.core.ports import EvalItem, EvalReport
from vlade_rag.evaluation import metrics as m

FETCH_FACTOR = 5
RERANK_TOP_N_LIMIT = 100  # the upper bound of ``RerankConfig.top_n``
DEFAULT_CUTOFFS = (1, 3, 5, 10)


class RetrievalEvaluator:
    name = "retrieval"

    def __init__(
        self,
        deps: Dependencies,
        cutoffs: Sequence[int] = DEFAULT_CUTOFFS,
        rerank: RerankConfig | None = None,
    ) -> None:
        """``rerank`` replaces the reranker of the base for this run. The base is not changed."""
        if not cutoffs or any(c < 1 for c in cutoffs):
            raise InvalidArgument("The cutoffs must be whole numbers of 1 or more.")
        self.deps = deps
        self.cutoffs = tuple(sorted(set(cutoffs)))
        self.rerank = rerank

    async def evaluate(
        self, ctx: TenantContext, kb: KnowledgeBase, items: Sequence[EvalItem], k: int
    ) -> EvalReport:
        """Score the retrieval of ``kb`` for ``items``. ``k`` is the largest cutoff."""
        ctx.require(Role.ADMIN)
        if k < 1:
            raise InvalidArgument("k must be 1 or more.")
        scored = [item for item in items if self._relevant(item)]
        if not scored:
            raise InvalidArgument("No question has a relevant document.")
        cutoffs = tuple(sorted({c for c in self.cutoffs if c <= k} | {k}))
        fetch = min(k * FETCH_FACTOR, self.deps.limits.max_top_k)
        kb = self._with_rerank(kb, fetch)
        search = Search(self.deps)

        per_metric: dict[str, list[float]] = {}
        details: list[dict[str, Any]] = []
        for item in scored:
            query = Query(item.question, kb.id)
            chunks = await search.run(ctx, kb, query, fetch)
            # The metrics compare against everything the dataset names, found or not.
            relevant = self._relevant_keys(item)
            documents = m.unique_in_order(
                (str(c.chunk.document_id), c.chunk.document_title) for c in chunks
            )
            keys = m.unique_in_order(self._key(doc, title, relevant) for doc, title in documents)
            for cutoff in cutoffs:
                per_metric.setdefault(f"recall@{cutoff}", []).append(
                    m.recall_at_k(keys, relevant, cutoff)
                )
                per_metric.setdefault(f"precision@{cutoff}", []).append(
                    m.precision_at_k(keys, relevant, cutoff)
                )
                per_metric.setdefault(f"ndcg@{cutoff}", []).append(
                    m.ndcg_at_k(keys, relevant, cutoff)
                )
            per_metric.setdefault("mrr", []).append(m.reciprocal_rank(keys, relevant))
            details.append(
                {
                    "question": item.question,
                    "relevant_documents": sorted(relevant),
                    "retrieved_documents": [title for _, title in documents[:k]],
                    "first_relevant_rank": m.first_relevant_rank(keys, relevant),
                }
            )
        report_metrics = {name: round(m.mean(values), 6) for name, values in per_metric.items()}
        return EvalReport(
            metrics=report_metrics,
            config=self._config(kb, len(scored), len(items), cutoffs, fetch),
            items=len(scored),
            details=tuple(details),
        )

    # ------------------------------------------------------------ helpers

    def _with_rerank(self, kb: KnowledgeBase, fetch: int) -> KnowledgeBase:
        """Apply the reranker of this run. The reranker returns ``top_n`` chunks, so ``top_n``
        rises to the number of chunks fetched. A lower ``top_n`` would cut the ranking short and
        lower Recall@K for a reason that is not the quality of the reranker."""
        retrieval = kb.config.retrieval
        rerank = self.rerank or retrieval.rerank
        if not rerank.enabled:
            return kb
        rerank = rerank.model_copy(
            update={"top_n": min(max(rerank.top_n, fetch), RERANK_TOP_N_LIMIT)}
        )
        retrieval = retrieval.model_copy(update={"rerank": rerank})
        return replace(kb, config=kb.config.model_copy(update={"retrieval": retrieval}))

    @staticmethod
    def _relevant(item: EvalItem) -> bool:
        return bool(item.relevant_document_titles or item.relevant_document_ids)

    @staticmethod
    def _relevant_keys(item: EvalItem) -> set[str]:
        """The titles and the ids (as text) of the documents the dataset names."""
        return set(item.relevant_document_titles) | {str(i) for i in item.relevant_document_ids}

    @staticmethod
    def _key(document_id: str, title: str, relevant: set[str]) -> str:
        """The key of a retrieved document: its id or its title, whichever the dataset names."""
        if document_id in relevant and title not in relevant:
            return document_id
        return title

    def _config(
        self,
        kb: KnowledgeBase,
        scored: int,
        total: int,
        cutoffs: tuple[int, ...],
        fetch: int,
    ) -> Mapping[str, object]:
        return {
            "evaluator": self.name,
            "vlade_rag_version": __version__,
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "knowledge_base": {"slug": kb.slug, "id": str(kb.id), "epoch": kb.epoch},
            "knowledge_base_config": kb.config.model_dump(mode="json"),
            "questions": {"scored": scored, "in_dataset": total},
            "cutoffs": list(cutoffs),
            "chunks_fetched_per_question": fetch,
            "unit": "document (each document counts once, at the rank of its best chunk)",
        }
