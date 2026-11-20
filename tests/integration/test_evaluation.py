"""The retrieval evaluator end to end. Runs with memory and PostgreSQL (see ``world``)."""

from __future__ import annotations

import pytest

from tests.conftest import World
from vlade_rag.core.application import CreateKnowledgeBase, SubmitIngestion
from vlade_rag.core.domain import (
    InvalidArgument,
    KnowledgeBase,
    KnowledgeBaseConfig,
    PermissionDenied,
    RawDocument,
)
from vlade_rag.core.domain.kb_config import ChunkingConfig, EmbeddingsConfig
from vlade_rag.core.ports import EvalItem
from vlade_rag.evaluation.retrieval import RetrievalEvaluator

pytestmark = pytest.mark.anyio

DOCS = {
    "prazos.md": "# Prazos\n\nO prazo de entrega padrão é de cinco dias úteis para todo o país.",
    "garantia.md": "# Garantia\n\nA garantia dos equipamentos é de um ano a partir da compra.",
    "pagamento.md": "# Pagamento\n\nAceitamos boleto, cartão de crédito e Pix, em até doze vezes.",
}


@pytest.fixture
async def kb(world: World) -> tuple[World, KnowledgeBase]:
    config = KnowledgeBaseConfig(
        chunking=ChunkingConfig(strategy="markdown", max_tokens=40, overlap_tokens=5),
        embeddings=EmbeddingsConfig(provider="hashing", model="hashing-v1", dimension=64),
    )
    created = await CreateKnowledgeBase(world.deps).execute(
        world.admin, slug="vendas", name="Vendas", config=config
    )
    for name, text in DOCS.items():
        await SubmitIngestion(world.deps).execute(
            world.admin,
            knowledge_base="vendas",
            raw=RawDocument(filename=name, mime_type="text/markdown", data=text.encode()),
        )
    await world.drain_jobs()
    return world, created


def item(question: str, *titles: str) -> EvalItem:
    return EvalItem(question=question, relevant_document_titles=titles)


async def test_scores_a_dataset_and_records_the_configuration(
    kb: tuple[World, KnowledgeBase],
) -> None:
    world, base = kb
    items = [
        item("prazo de entrega padrão cinco dias úteis", "prazos.md"),
        item("garantia dos equipamentos um ano", "garantia.md"),
        # Two documents are named, and only one exists: recall can reach at most 0.5.
        item("prazo de entrega", "prazos.md", "nao-existe.md"),
        EvalItem(question="sem documento relevante"),  # skipped: nothing to score
    ]
    report = await RetrievalEvaluator(world.deps).evaluate(world.admin, base, items, 10)

    assert report.items == 3
    assert report.config["questions"] == {"scored": 3, "in_dataset": 4}
    assert report.metrics["recall@10"] == pytest.approx((1 + 1 + 0.5) / 3, abs=1e-5)
    assert report.metrics["mrr"] == 1.0
    assert report.metrics["precision@1"] == 1.0
    assert report.metrics["ndcg@10"] < 1.0  # the missing document keeps NDCG below 1
    assert {"recall@1", "recall@3", "recall@5", "recall@10", "ndcg@5", "precision@3"} <= set(
        report.metrics
    )
    assert all(0.0 <= v <= 1.0 for v in report.metrics.values())

    # RF-72: the configuration of the run is recorded, with the whole configuration of the base.
    config = report.config
    assert config["knowledge_base"]["slug"] == "vendas"  # type: ignore[index]
    assert config["knowledge_base_config"]["embeddings"]["model"] == "hashing-v1"  # type: ignore[index]
    assert config["knowledge_base_config"]["retrieval"]["retrievers"]  # type: ignore[index]
    assert config["cutoffs"] == [1, 3, 5, 10] and config["vlade_rag_version"] and config["date"]

    first = report.details[0]
    assert first["first_relevant_rank"] == 1 and first["retrieved_documents"][0] == "prazos.md"
    assert report.details[2]["relevant_documents"] == ["nao-existe.md", "prazos.md"]


async def test_a_question_whose_document_is_not_retrieved_scores_zero(
    kb: tuple[World, KnowledgeBase],
) -> None:
    world, base = kb
    report = await RetrievalEvaluator(world.deps).evaluate(
        world.admin, base, [item("boleto cartão Pix doze vezes", "nao-existe.md")], 5
    )
    assert report.metrics["recall@5"] == 0.0 and report.metrics["mrr"] == 0.0
    assert report.details[0]["first_relevant_rank"] is None


async def test_the_cutoffs_follow_k(kb: tuple[World, KnowledgeBase]) -> None:
    world, base = kb
    report = await RetrievalEvaluator(world.deps).evaluate(
        world.admin, base, [item("garantia dos equipamentos", "garantia.md")], 3
    )
    assert report.config["cutoffs"] == [1, 3]
    assert "recall@5" not in report.metrics and "recall@3" in report.metrics


async def test_only_an_administrator_evaluates(kb: tuple[World, KnowledgeBase]) -> None:
    world, base = kb
    with pytest.raises(PermissionDenied):
        await RetrievalEvaluator(world.deps).evaluate(
            world.reader, base, [item("garantia", "garantia.md")], 5
        )


async def test_invalid_input_is_refused(kb: tuple[World, KnowledgeBase]) -> None:
    world, base = kb
    evaluator = RetrievalEvaluator(world.deps)
    with pytest.raises(InvalidArgument):
        await evaluator.evaluate(world.admin, base, [item("q", "a.md")], 0)
    with pytest.raises(InvalidArgument, match="No question"):
        await evaluator.evaluate(world.admin, base, [EvalItem(question="q")], 5)
    with pytest.raises(InvalidArgument):
        RetrievalEvaluator(world.deps, cutoffs=[0])
