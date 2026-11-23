"""Recall@10 of pgvector and Qdrant on the same space (roadmap task 5.1).

pgvector stays the default and the reference. The test ingests once with pgvector, copies the
vectors to an in-process Qdrant client and runs the same evaluation with both indexes. A
difference above two percentage points fails the acceptance criterion.
"""

from __future__ import annotations

import pytest

pytest.importorskip("qdrant_client")

from qdrant_client import AsyncQdrantClient

from tests.conftest import World
from vlade_rag.core.application import CreateKnowledgeBase, SubmitIngestion
from vlade_rag.core.domain import KnowledgeBaseConfig, RawDocument
from vlade_rag.core.domain.kb_config import EmbeddingsConfig
from vlade_rag.core.ports import EvalItem
from vlade_rag.evaluation.retrieval import RetrievalEvaluator
from vlade_rag.knowledge.qdrant import QdrantVectorIndex

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

DIMENSION = 64
DOCS = (
    ("O prazo para responder é de dez dias.", "prazo.md"),
    ("O recurso pode ser pedido em quinze dias.", "recurso.md"),
    ("A auditoria guarda os eventos por seis meses.", "auditoria.md"),
    ("Os dados pessoais são sigilosos e protegidos.", "sigilo.md"),
    ("A revisão do contrato acontece uma vez por ano.", "revisao.md"),
    ("O fornecedor deve apresentar a nota fiscal.", "fornecedor.md"),
    ("A fatura é paga em trinta dias após o recebimento.", "fatura.md"),
    ("O cliente pode cancelar o pedido antes do envio.", "cancelamento.md"),
    ("A senha do usuário precisa de oito caracteres.", "senha.md"),
    ("O relatório mensal resume as vendas do mês.", "relatorio.md"),
)
ITEMS = tuple(
    EvalItem(question=question, relevant_document_titles=(title,))
    for question, title in (
        ("Qual é o prazo para responder?", "prazo.md"),
        ("Quando pedir recurso?", "recurso.md"),
        ("Por quanto tempo a auditoria guarda eventos?", "auditoria.md"),
        ("Como são protegidos os dados pessoais?", "sigilo.md"),
        ("Quando acontece a revisão do contrato?", "revisao.md"),
        ("O que o fornecedor apresenta?", "fornecedor.md"),
    )
)


async def test_pgvector_and_qdrant_have_equivalent_recall(world: World) -> None:
    if world.backend != "postgres":
        pytest.skip("the comparison needs pgvector in PostgreSQL")
    config = KnowledgeBaseConfig(
        embeddings=EmbeddingsConfig(provider="h", model="h", dimension=DIMENSION)
    )
    await CreateKnowledgeBase(world.deps).execute(world.admin, slug="kb", name="KB", config=config)
    for text, title in DOCS:
        await SubmitIngestion(world.deps).execute(
            world.admin,
            knowledge_base="kb",
            raw=RawDocument(title, "text/markdown", text.encode("utf-8")),
        )
    await world.drain_jobs()
    kb = await world.deps.repository.get_knowledge_base(world.admin, "kb")
    space = await world.deps.repository.get_embedding_space(
        world.admin, kb.active_embedding_space_id
    )

    # Cache would make the second evaluation replay the first one.
    world.deps.cache = None
    evaluator = RetrievalEvaluator(world.deps)
    pg = await evaluator.evaluate(world.admin, kb, ITEMS, 10)

    client = AsyncQdrantClient(location=":memory:")
    qdrant = QdrantVectorIndex(client, world.deps.repository)
    try:
        await qdrant.ensure_space(world.admin, space)
        async with world.extra["db"].tenant(world.admin) as conn:
            rows = await conn.fetch(
                "SELECT chunk_id, embedding FROM chunk_embeddings WHERE embedding_space_id = $1",
                space.id,
            )
        await qdrant.upsert(
            world.admin,
            space,
            kb.id,
            [(row["chunk_id"], row["embedding"].to_list()) for row in rows],
        )
        world.deps.vector_index = qdrant
        qd = await evaluator.evaluate(world.admin, kb, ITEMS, 10)
    finally:
        await client.close()

    pg_recall = pg.metrics["recall@10"]
    qd_recall = qd.metrics["recall@10"]
    assert abs(pg_recall - qd_recall) <= 0.02, (pg_recall, qd_recall)
    assert pg_recall > 0, "the comparison needs at least one relevant retrieval"
