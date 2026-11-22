"""Scheduled evaluation of a knowledge base (ADR-0011, MCP_SPEC section 5.10)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.domain import (
    AuditEvent,
    IngestionJob,
    InvalidArgument,
    JobKind,
    NotFound,
    Role,
    TenantContext,
)

# The nightly flow scores retrieval. Answer metrics need a paid judge and stay in the CLI.
SUPPORTED_METRICS = frozenset({"recall_at_k", "precision_at_k", "mrr", "ndcg"})
DEFAULT_K = 10


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    job: IngestionJob
    dataset: str
    items: int
    k: int
    metrics: tuple[str, ...]


class RunEvaluation:
    """Validate a registered dataset and enqueue an ``evaluation`` job."""

    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps

    async def execute(
        self,
        ctx: TenantContext,
        *,
        knowledge_base: str,
        dataset: str,
        metrics: Sequence[str] | None = None,
        k: int | None = None,
    ) -> EvaluationResult:
        ctx.require(Role.ADMIN)
        registry = self.deps.evaluation_datasets
        if registry is None:
            raise InvalidArgument("The evaluation datasets are not configured on this server.")
        kb = await self.deps.repository.get_knowledge_base(ctx, knowledge_base)
        if dataset not in await registry.list_names():
            raise NotFound(f"The dataset '{dataset}' does not exist.")
        items = await registry.load(dataset)

        chosen = tuple(dict.fromkeys(metrics)) if metrics else tuple(sorted(SUPPORTED_METRICS))
        unsupported = sorted(set(chosen) - SUPPORTED_METRICS)
        if unsupported:
            raise InvalidArgument(f"Unsupported metrics for a scheduled evaluation: {unsupported}.")
        top_k = DEFAULT_K if k is None else k
        if not 1 <= top_k <= self.deps.limits.max_top_k:
            raise InvalidArgument(f"'k' must be between 1 and {self.deps.limits.max_top_k}.")

        job = await self.deps.job_queue.enqueue(
            ctx,
            kind=JobKind.EVALUATION,
            knowledge_base_id=kb.id,
            input={
                "knowledge_base": kb.slug,
                "dataset": dataset,
                "metrics": list(chosen),
                "k": top_k,
            },
        )
        await self.deps.audit_log.record(
            ctx,
            AuditEvent(
                tenant_id=ctx.tenant_id,
                principal_id=ctx.principal_id,
                interface=ctx.interface,
                action="evaluation.submit",
                outcome="success",
                resource_type="knowledge_base",
                resource_id=str(kb.id),
                details={"job_id": str(job.id), "dataset": dataset, "items": len(items)},
                trace_id=ctx.trace_id,
            ),
        )
        return EvaluationResult(job=job, dataset=dataset, items=len(items), k=top_k, metrics=chosen)
