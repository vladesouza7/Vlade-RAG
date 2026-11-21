"""Quality gate for the CI (RF-73, roadmap 3.9, ADR-0024).

The gate builds one throwaway knowledge base per dataset, runs the retrieval evaluation of each
configured run and compares the metrics with a baseline. It fails when a metric drops more than
the configured limit. The embeddings are ``hashing``, so the gate calls no provider and gives the
same numbers on every run with the same code.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vlade_rag.core.application import CreateKnowledgeBase, SubmitIngestion
from vlade_rag.core.domain import RawDocument, Role, TenantContext
from vlade_rag.core.domain.kb_config import QueryTransform, RetrieverName
from vlade_rag.evaluation.datasets import load_dataset
from vlade_rag.evaluation.retrieval import RetrievalEvaluator

DOCUMENT_SUFFIXES = {".md": "text/markdown", ".txt": "text/plain"}


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GateRun(_Strict):
    """One evaluation: a dataset, a question file and the retrieval settings of the run."""

    name: str = Field(min_length=1)
    dataset: str = Field(min_length=1)  # a folder with docs/ and the question file
    questions: str = "questions.jsonl"
    retrievers: tuple[RetrieverName, ...] = ("dense", "lexical")
    query_transform: QueryTransform | None = None


class GateConfig(_Strict):
    """The gate file (``evals/gate/gate.json``). Paths are relative to the repository root."""

    max_drop: float = Field(default=0.02, ge=0, le=1)  # the largest allowed drop of a metric
    metrics: tuple[str, ...] = ("recall@10", "mrr", "ndcg@10")
    k: int = Field(default=10, ge=1)
    knowledge_base: dict[str, Any] = Field(default_factory=dict)  # KnowledgeBaseConfig fields
    runs: tuple[GateRun, ...]

    @model_validator(mode="after")
    def _unique_names(self) -> GateConfig:
        names = [r.name for r in self.runs]
        if len(names) != len(set(names)):
            raise ValueError("every run needs a different name")
        if not self.runs:
            raise ValueError("at least one run is required")
        return self


@dataclass(frozen=True, slots=True)
class MetricCheck:
    run: str
    metric: str
    baseline: float | None
    value: float
    max_drop: float

    @property
    def drop(self) -> float:
        return 0.0 if self.baseline is None else round(self.baseline - self.value, 6)

    @property
    def change(self) -> float:
        """The value minus the baseline: negative when the metric dropped."""
        return 0.0 if self.baseline is None else round(self.value - self.baseline, 6) + 0.0

    @property
    def failed(self) -> bool:
        return self.baseline is not None and self.drop > self.max_drop + 1e-9


@dataclass(frozen=True, slots=True)
class GateResult:
    checks: tuple[MetricCheck, ...]
    metrics: Mapping[str, Mapping[str, float]]  # run -> metric -> value
    missing_baseline: tuple[str, ...] = field(default_factory=tuple)  # "run/metric" without one

    @property
    def passed(self) -> bool:
        return not any(c.failed for c in self.checks) and not self.missing_baseline


def load_config(path: str | Path) -> GateConfig:
    return GateConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_baseline(path: str | Path) -> dict[str, dict[str, float]]:
    file = Path(path)
    if not file.exists():
        return {}
    data = json.loads(file.read_text(encoding="utf-8"))
    return {run: dict(values) for run, values in data.get("runs", {}).items()}


def baseline_payload(metrics: Mapping[str, Mapping[str, float]]) -> dict[str, Any]:
    return {
        "note": "Written by 'vlade-rag eval gate --update-baseline'. Review every change.",
        "runs": {run: dict(sorted(values.items())) for run, values in sorted(metrics.items())},
    }


def compare(
    config: GateConfig,
    metrics: Mapping[str, Mapping[str, float]],
    baseline: Mapping[str, Mapping[str, float]],
) -> GateResult:
    checks: list[MetricCheck] = []
    missing: list[str] = []
    for run in config.runs:
        for metric in config.metrics:
            value = metrics[run.name][metric]
            reference = baseline.get(run.name, {}).get(metric)
            if reference is None:
                missing.append(f"{run.name}/{metric}")
            checks.append(MetricCheck(run.name, metric, reference, value, config.max_drop))
    return GateResult(tuple(checks), metrics, tuple(missing))


async def run_gate(runtime: Any, config: GateConfig, root: str | Path = ".") -> GateResult:
    """Evaluate every run of ``config``. ``compare`` checks the result against a baseline."""
    root = Path(root)
    deps = runtime.deps
    tenant = await runtime.tenants.create_tenant(f"gate-{secrets.token_hex(4)}", "Quality gate")
    issued = await runtime.tenants.issue_api_key(
        tenant.id, principal_name="gate", roles=frozenset({Role.ADMIN})
    )
    ctx: TenantContext = await runtime.tenants.authenticate(issued.key, interface="cli")
    bases: dict[str, str] = {}
    metrics: dict[str, dict[str, float]] = {}
    for run in config.runs:
        if run.dataset not in bases:
            bases[run.dataset] = await _ingest(runtime, ctx, root / run.dataset, len(bases), config)
        kb = await deps.repository.get_knowledge_base(ctx, bases[run.dataset])
        items = load_dataset(root / run.dataset / run.questions)
        evaluator = RetrievalEvaluator(
            deps, retrievers=run.retrievers, query_transform=run.query_transform
        )
        report = await evaluator.evaluate(ctx, kb, items, config.k)
        metrics[run.name] = {m: report.metrics[m] for m in config.metrics}
    return GateResult((), metrics)


async def _ingest(
    runtime: Any, ctx: TenantContext, folder: Path, number: int, config: GateConfig
) -> str:
    from vlade_rag.ingestion.worker import Worker

    slug = f"gate-{number}"
    await CreateKnowledgeBase(runtime.deps).execute(
        ctx, slug=slug, name=folder.name, config=config.knowledge_base
    )
    submit = SubmitIngestion(runtime.deps)
    files = sorted(p for p in (folder / "docs").iterdir() if p.suffix in DOCUMENT_SUFFIXES)
    for path in files:
        await submit.execute(
            ctx,
            knowledge_base=slug,
            raw=RawDocument(
                filename=path.name,
                mime_type=DOCUMENT_SUFFIXES[path.suffix],
                data=path.read_bytes(),
            ),
        )
    await Worker(runtime, worker_id="gate").run_until_idle()
    return slug


def format_result(result: GateResult, config: GateConfig) -> Sequence[str]:
    lines = [f"Quality gate: a metric may drop at most {config.max_drop:.4f}."]
    for c in result.checks:
        reference = "none" if c.baseline is None else f"{c.baseline:.4f}"
        mark = "FAIL" if c.failed else ("NEW " if c.baseline is None else "ok  ")
        lines.append(
            f"  {mark} {c.run:<32} {c.metric:<12} {c.value:.4f} (baseline {reference}, "
            f"change {c.change:+.4f})"
        )
    if result.missing_baseline:
        lines.append(
            "Some metrics have no baseline. Run 'vlade-rag eval gate --update-baseline' and "
            "commit the file."
        )
    lines.append("PASSED" if result.passed else "FAILED")
    return lines
