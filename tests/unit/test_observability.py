import json
import logging

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tests.conftest import World
from vlade_rag.core.application import AnswerQuery, CreateKnowledgeBase, SubmitIngestion
from vlade_rag.core.domain import KnowledgeBaseConfig, RawDocument
from vlade_rag.core.domain.kb_config import EmbeddingsConfig
from vlade_rag.observability.logging import JsonFormatter
from vlade_rag.observability.opentelemetry import OtelTracer


@pytest.mark.anyio
async def test_query_pipeline_spans(world: World) -> None:
    if world.backend != "memory":
        pytest.skip("span names do not depend on the backend")
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = OtelTracer(provider.get_tracer("test"))
    world.deps.tracer = tracer
    config = KnowledgeBaseConfig(embeddings=EmbeddingsConfig(provider="h", model="h", dimension=64))
    await CreateKnowledgeBase(world.deps).execute(world.admin, slug="kb", name="KB", config=config)
    await SubmitIngestion(world.deps).execute(
        world.admin,
        knowledge_base="kb",
        raw=RawDocument("a.md", "text/markdown", "# A\n\nO prazo é de dez dias.".encode()),
    )
    await world.drain_jobs()
    exporter.clear()
    with tracer.span("request"):
        answer = await AnswerQuery(world.deps).execute(
            world.reader, knowledge_base="kb", question="Qual é o prazo?"
        )
    names = {s.name for s in exporter.get_finished_spans()}
    assert {
        "query_analysis",
        "retrieval.dense",
        "retrieval.lexical",
        "fusion",
        "context_assembly",
        "llm_generation",
        "response_validation",
    } <= names
    assert answer.trace_id is not None and len(answer.trace_id) == 32


def test_json_logs_redact_secrets() -> None:
    record = logging.LogRecord("vlade", logging.INFO, "f", 1, "hello %s", ("world",), None)
    record.api_key = "vrag_secret"
    record.tenant_id = "t1"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "hello world"
    assert payload["api_key"] == "[REDACTED]"
    assert payload["tenant_id"] == "t1"


async def _traced_query(world: World, store_text: bool) -> dict[str, dict[str, object]]:
    from dataclasses import replace

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    world.deps.tracer = OtelTracer(provider.get_tracer("test"))
    world.deps.limits = replace(world.deps.limits, store_query_text=store_text)
    config = KnowledgeBaseConfig(embeddings=EmbeddingsConfig(provider="h", model="h", dimension=64))
    await CreateKnowledgeBase(world.deps).execute(world.admin, slug="kb", name="KB", config=config)
    await SubmitIngestion(world.deps).execute(
        world.admin,
        knowledge_base="kb",
        raw=RawDocument("a.md", "text/markdown", "# A\n\nO prazo é de dez dias.".encode()),
    )
    await world.drain_jobs()
    exporter.clear()
    await AnswerQuery(world.deps).execute(
        world.reader, knowledge_base="kb", question="Qual é o prazo?"
    )
    return {s.name: dict(s.attributes or {}) for s in exporter.get_finished_spans()}


@pytest.mark.anyio
@pytest.mark.parametrize("store_text", [False, True])
async def test_ai_spans_follow_openinference(world: World, store_text: bool) -> None:
    """Phoenix reads these attributes (ADR-0026). Text goes in only with store_query_text."""
    if world.backend != "memory":
        pytest.skip("span attributes do not depend on the backend")
    spans = await _traced_query(world, store_text)
    kind = "openinference.span.kind"
    assert spans["query"][kind] == "CHAIN"
    assert spans["query_analysis"][kind] == "RETRIEVER"
    assert spans["retrieval.dense"][kind] == "RETRIEVER"
    assert spans["fusion"][kind] == "CHAIN"
    llm = spans["llm_generation"]
    assert llm[kind] == "LLM"
    assert llm["llm.model_name"] == "qwen3:8b"
    assert llm["llm.token_count.total"] == (
        llm["llm.token_count.prompt"] + llm["llm.token_count.completion"]
    )
    assert spans["query_analysis"]["retrieval.documents.0.document.id"]
    texts = [
        spans["query"].get("input.value"),
        spans["query"].get("output.value"),
        llm.get("input.value"),
        llm.get("output.value"),
        spans["query_analysis"].get("retrieval.documents.0.document.content"),
    ]
    if store_text:
        assert spans["query"]["input.value"] == "Qual é o prazo?"
        assert all(texts)
    else:
        assert texts == [None] * 5


@pytest.mark.anyio
async def test_build_runtime_gives_the_tracer_to_the_use_cases() -> None:
    """Regression: build_runtime took a tracer and dropped it, so no use case span was sent."""
    from vlade_rag.bootstrap import build_runtime
    from vlade_rag.core.config import Settings

    tracer = OtelTracer(TracerProvider().get_tracer("test"))
    settings = Settings(storage={"backend": "memory"}, object_storage={"backend": "memory"})  # type: ignore[arg-type]
    runtime = await build_runtime(settings, tracer=tracer, load_plugins=False)
    try:
        assert runtime.deps.tracer is tracer
    finally:
        await runtime.aclose()
