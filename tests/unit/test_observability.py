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
