"""Worker side of an ``evaluation`` job (ADR-0011)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import IngestionJob, InvalidArgument, Metadata, NotFound, TenantContext
from vlade_rag.evaluation.retrieval import RetrievalEvaluator

_PREFIXES: dict[str, str] = {
    "recall_at_k": "recall@",
    "precision_at_k": "precision@",
    "ndcg": "ndcg@",
}


def select_metrics(metrics: Mapping[str, float], wanted: Sequence[str]) -> dict[str, float]:
    """Keep the metric families requested by the job."""
    selected: dict[str, float] = {}
    for name, value in metrics.items():
        for family in wanted:
            prefix = _PREFIXES.get(family)
            if (family == "mrr" and name == "mrr") or (
                prefix is not None and name.startswith(prefix)
            ):
                selected[name] = value
    return selected


class EvaluationWorker:
    """Score a registered dataset and return the report as the job result."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def run(self, ctx: TenantContext, job: IngestionJob) -> Metadata:
        registry = self.deps.evaluation_datasets
        if registry is None:
            raise InvalidArgument("The evaluation datasets are not configured on this server.")
        name = str(job.input["dataset"])
        if name not in await registry.list_names():
            raise NotFound(f"The dataset '{name}' does not exist.")
        items = await registry.load(name)
        kb = await self.deps.repository.get_knowledge_base(ctx, str(job.input["knowledge_base"]))
        k = int(job.input.get("k", 10))
        wanted = tuple(str(m) for m in job.input.get("metrics", ()))
        report = await RetrievalEvaluator(self.deps).evaluate(ctx, kb, items, k)
        result: dict[str, Any] = {
            "dataset": name,
            "items": report.items,
            "metrics": select_metrics(report.metrics, wanted),
            "config": dict(report.config),
        }
        return result
