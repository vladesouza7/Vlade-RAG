"""Tests for the application metric catalogue (ARCHITECTURE section 16.2)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import World
from vlade_rag.core.application import AnswerQuery, CreateKnowledgeBase, SubmitIngestion
from vlade_rag.core.domain import JobKind, KnowledgeBaseConfig, RawDocument
from vlade_rag.core.domain.kb_config import EmbeddingsConfig


class RecordingMetrics:
    def __init__(self) -> None:
        self.counters: list[tuple[str, float, dict[str, Any]]] = []
        self.histograms: list[tuple[str, float, dict[str, Any]]] = []
        self.gauges: list[tuple[str, float, dict[str, Any]]] = []

    def counter(self, name: str, value: float = 1, attributes: Any = None) -> None:
        self.counters.append((name, value, dict(attributes or {})))

    def histogram(self, name: str, value: float, attributes: Any = None) -> None:
        self.histograms.append((name, value, dict(attributes or {})))

    def gauge(self, name: str, value: float, attributes: Any = None) -> None:
        self.gauges.append((name, value, dict(attributes or {})))

    def llm_usage(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
        labels = {"provider": provider, "model": model}
        self.counter("vlade_llm_tokens_total", input_tokens, {**labels, "direction": "input"})
        self.counter("vlade_llm_tokens_total", output_tokens, {**labels, "direction": "output"})
        self.counter("vlade_llm_cost_usd_total", 0.0, labels)


def _assert_no_tenant_label(records: list[tuple[str, float, dict[str, Any]]]) -> None:
    for _, _, attributes in records:
        assert "tenant_id" not in attributes


@pytest.mark.anyio
async def test_query_records_the_metric_catalogue(world: World) -> None:
    if world.backend != "memory":
        pytest.skip("the metric names do not depend on the backend")
    metrics = RecordingMetrics()
    world.deps.metrics = metrics
    config = KnowledgeBaseConfig(embeddings=EmbeddingsConfig(provider="h", model="h", dimension=64))
    await CreateKnowledgeBase(world.deps).execute(world.admin, slug="kb", name="KB", config=config)
    await SubmitIngestion(world.deps).execute(
        world.admin,
        knowledge_base="kb",
        raw=RawDocument("a.md", "text/markdown", "# A\n\nO prazo é de dez dias.".encode()),
    )
    await world.drain_jobs()
    metrics.counters.clear()
    metrics.histograms.clear()
    await AnswerQuery(world.deps).execute(
        world.reader, knowledge_base="kb", question="Qual é o prazo?"
    )

    names = {name for name, _, _ in metrics.counters}
    assert {
        "vlade_requests_total",
        "vlade_answers_grounded_total",
        "vlade_llm_tokens_total",
        "vlade_llm_cost_usd_total",
    } <= names
    assert (
        "vlade_requests_total",
        1,
        {"interface": "library", "operation": "query", "outcome": "success"},
    ) in metrics.counters
    assert any(name == "vlade_request_duration_seconds" for name, _, _ in metrics.histograms)
    assert any(name == "vlade_stage_duration_seconds" for name, _, _ in metrics.histograms)
    assert any(name == "vlade_retrieval_results" for name, _, _ in metrics.histograms)
    _assert_no_tenant_label(metrics.counters)
    _assert_no_tenant_label(metrics.histograms)


@pytest.mark.anyio
async def test_ingestion_records_jobs_and_stages(world: World) -> None:
    if world.backend != "memory":
        pytest.skip("the metric names do not depend on the backend")
    metrics = RecordingMetrics()
    world.deps.metrics = metrics
    config = KnowledgeBaseConfig(embeddings=EmbeddingsConfig(provider="h", model="h", dimension=64))
    await CreateKnowledgeBase(world.deps).execute(world.admin, slug="kb", name="KB", config=config)
    await SubmitIngestion(world.deps).execute(
        world.admin,
        knowledge_base="kb",
        raw=RawDocument("a.md", "text/markdown", "# A\n\nO prazo é de dez dias.".encode()),
    )
    await world.drain_jobs()

    names = {name for name, _, _ in metrics.counters}
    assert "vlade_ingestion_jobs_total" in names
    assert (
        "vlade_ingestion_jobs_total",
        1,
        {"kind": "ingest", "status": "submitted"},
    ) in metrics.counters
    assert (
        "vlade_ingestion_jobs_total",
        1,
        {"kind": "ingest", "status": "success"},
    ) in metrics.counters
    assert any(name == "vlade_stage_duration_seconds" for name, _, _ in metrics.histograms)
    _assert_no_tenant_label(metrics.counters)
    _assert_no_tenant_label(metrics.histograms)


@pytest.mark.anyio
async def test_job_queue_reports_pending_depth(world: World) -> None:
    assert await world.deps.job_queue.pending_count(JobKind.INGEST) == 0
    config = KnowledgeBaseConfig(embeddings=EmbeddingsConfig(provider="h", model="h", dimension=64))
    await CreateKnowledgeBase(world.deps).execute(world.admin, slug="kb", name="KB", config=config)
    await SubmitIngestion(world.deps).execute(
        world.admin,
        knowledge_base="kb",
        raw=RawDocument("a.md", "text/markdown", b"# A"),
    )
    assert await world.deps.job_queue.pending_count(JobKind.INGEST) == 1


@pytest.mark.anyio
async def test_build_runtime_gives_the_metrics_to_the_use_cases() -> None:
    from vlade_rag.bootstrap import build_runtime
    from vlade_rag.core.config import Settings

    metrics = RecordingMetrics()
    settings = Settings(storage={"backend": "memory"}, object_storage={"backend": "memory"})  # type: ignore[arg-type]
    runtime = await build_runtime(settings, metrics=metrics, load_plugins=False)
    try:
        assert runtime.deps.metrics is metrics
    finally:
        await runtime.aclose()


def test_otel_metrics_keep_the_catalogue_names_and_estimate_cost() -> None:
    pytest.importorskip("opentelemetry.sdk.metrics")
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    from vlade_rag.observability.opentelemetry import OtelMetrics

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics = OtelMetrics(provider.get_meter("test"))
    metrics.counter(
        "vlade_requests_total", 1, {"interface": "api", "operation": "GET", "outcome": "success"}
    )
    metrics.llm_usage("openai", "gpt-4o-mini", 1_000_000, 1_000_000)

    data = reader.get_metrics_data()
    assert data is not None
    names = {
        metric.name
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }
    assert names == {"vlade_requests_total", "vlade_llm_tokens_total", "vlade_llm_cost_usd_total"}
    cost = next(
        point.value
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == "vlade_llm_cost_usd_total"
        for point in metric.data.data_points
    )
    assert cost == pytest.approx(0.75)  # 0.15 USD/M input + 0.60 USD/M output
