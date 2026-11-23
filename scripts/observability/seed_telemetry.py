"""Generate a small amount of real telemetry for the dashboards (task 4.6).

The script runs in one process with memory adapters. It creates a knowledge base, ingests a few
documents, searches and answers questions, then flushes the OTLP batches. Run it with telemetry
on and the Alloy endpoint set, for example::

    VLADE_STORAGE__BACKEND=memory VLADE_OBJECT_STORAGE__BACKEND=memory \\
    VLADE_OTEL__ENABLED=true VLADE_OTEL__ENDPOINT=http://127.0.0.1:4318 \\
    uv run python scripts/observability/seed_telemetry.py

The traces go to Tempo, the metrics to Prometheus and the JSON logs to stdout. When the script
runs in a container with the label ``com.docker.compose.project=vlade-rag``, Alloy also sends the
logs to Loki.
"""

from __future__ import annotations

import asyncio
import logging

from vlade_rag.bootstrap import build_runtime
from vlade_rag.core.application import (
    AnswerQuery,
    CreateKnowledgeBase,
    RunEvaluation,
    Search,
    SubmitIngestion,
)
from vlade_rag.core.config import get_settings
from vlade_rag.core.domain import KnowledgeBaseConfig, RawDocument, Role
from vlade_rag.core.domain.kb_config import EmbeddingsConfig, GenerationConfig
from vlade_rag.ingestion.worker import Worker
from vlade_rag.observability.opentelemetry import (
    flush_telemetry,
    setup_metrics,
    setup_telemetry,
)

logger = logging.getLogger("vlade_rag.seed")

DOCS = (
    "# Prazo\n\nO prazo para responder é de dez dias.",
    "# Recurso\n\nO recurso pode ser pedido em quinze dias.",
    "# Sigilo\n\nOs dados pessoais são sigilosos.",
    "# Auditoria\n\nA auditoria guarda os eventos por seis meses.",
    "# Revisão\n\nA revisão acontece uma vez por ano.",
)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = get_settings()
    tracer = setup_telemetry(settings)
    metrics = setup_metrics(settings)
    runtime = await build_runtime(settings, tracer=tracer, metrics=metrics, load_plugins=False)
    try:
        tenant = await runtime.tenants.create_tenant("demo-observabilidade", "Demo")
        key = await runtime.tenants.issue_api_key(
            tenant.id, principal_name="demo", roles=frozenset({Role.ADMIN})
        )
        ctx = await runtime.tenants.authenticate(key.key, interface="cli")
        config = KnowledgeBaseConfig(
            embeddings=EmbeddingsConfig(provider="hashing", model="hashing", dimension=64),
            generation=GenerationConfig(
                provider="extractive", model="extractive", require_citations=False
            ),
        )
        await CreateKnowledgeBase(runtime.deps).execute(
            ctx, slug="demo", name="Base de demonstração", config=config
        )
        for i, text in enumerate(DOCS):
            await SubmitIngestion(runtime.deps).execute(
                ctx,
                knowledge_base="demo",
                raw=RawDocument(f"doc-{i}.md", "text/markdown", text.encode("utf-8")),
            )
        await Worker(runtime).run_until_idle()
        logger.info("Job ingestion completed for %d documents", len(DOCS))
        for question in ("Qual é o prazo?", "Por quanto tempo guardam a auditoria?"):
            for _ in range(3):
                logger.info("seed search question=%s", question)
                await Search(runtime.deps).execute(
                    ctx, knowledge_base="demo", text=question, top_k=5
                )
                await AnswerQuery(runtime.deps).execute(
                    ctx, knowledge_base="demo", question=question
                )
        names = await runtime.deps.evaluation_datasets.list_names()
        if "legal-ptbr" in names:
            await RunEvaluation(runtime.deps).execute(
                ctx,
                knowledge_base="demo",
                dataset="legal-ptbr",
                metrics=["ndcg", "mrr"],
                k=10,
            )
            await Worker(runtime).run_until_idle()
    finally:
        await runtime.aclose()
        flush_telemetry()


if __name__ == "__main__":
    asyncio.run(main())
