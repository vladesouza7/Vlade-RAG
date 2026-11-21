"""Answer evaluation (RF-71, roadmap 3.7, ADR-0025).

The evaluator runs with memory and PostgreSQL (see ``world``) and a fake scorer, so no test calls
an LLM. ``RagasScorer`` is checked with stub metrics.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from tests.conftest import World
from vlade_rag.core.application import CreateKnowledgeBase, SubmitIngestion
from vlade_rag.core.domain import KnowledgeBaseConfig, RawDocument
from vlade_rag.core.domain.kb_config import ChunkingConfig, EmbeddingsConfig, RetrievalConfig
from vlade_rag.core.ports import EvalItem
from vlade_rag.evaluation.answers import AnswerEvaluator

pytestmark = pytest.mark.anyio

DOCS = {
    "garantia.md": "# Garantia\n\nA garantia dos equipamentos é de um ano a partir da compra.",
    "prazos.md": "# Prazos\n\nO prazo de entrega padrão é de cinco dias úteis para todo o país.",
}
ITEMS = [
    EvalItem("Qual é a garantia dos equipamentos?", expected_answer="Um ano a partir da compra."),
    EvalItem("Qual é o prazo de entrega?", expected_answer="Cinco dias úteis."),
    EvalItem("xyzzy qwerty", expected_answer=None),  # nothing matches: the answer is a refusal
]


class FakeScorer:
    name = "fake"
    metrics = ("faithfulness", "context_recall")

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[str, ...], str | None]] = []

    def describe(self) -> Mapping[str, object]:
        return {"judge_model": "none"}

    async def score(
        self, question: str, answer: str, contexts: Sequence[str], reference: str | None
    ) -> Mapping[str, float | None]:
        self.calls.append((question, answer, tuple(contexts), reference))
        if not contexts:
            return {"faithfulness": None, "context_recall": None}
        return {"faithfulness": 1.0, "context_recall": 0.5 if reference else float("nan")}


async def make_kb(world: World) -> Any:
    config = KnowledgeBaseConfig(
        chunking=ChunkingConfig(strategy="markdown", max_tokens=40, overlap_tokens=5),
        embeddings=EmbeddingsConfig(provider="hashing", model="hashing-v1", dimension=64),
        retrieval=RetrievalConfig(retrievers=("lexical",)),
    )
    kb = await CreateKnowledgeBase(world.deps).execute(
        world.admin, slug="vendas", name="Vendas", config=config
    )
    for name, text in DOCS.items():
        await SubmitIngestion(world.deps).execute(
            world.admin,
            knowledge_base="vendas",
            raw=RawDocument(filename=name, mime_type="text/markdown", data=text.encode()),
        )
    await world.drain_jobs()
    return kb


async def test_the_evaluator_scores_the_answer_and_the_context_of_the_flow(world: World) -> None:
    kb = await make_kb(world)
    scorer = FakeScorer()
    report = await AnswerEvaluator(world.deps, scorer, concurrency=2).evaluate(
        world.admin, kb, ITEMS
    )
    assert report.items == 3
    by_question = {c[0]: c for c in scorer.calls}
    _question, answer, contexts, reference = by_question["Qual é a garantia dos equipamentos?"]
    assert "um ano" in answer and "[1]" in answer  # the extractive LLM cites the first source
    assert any("garantia dos equipamentos" in c for c in contexts)
    assert reference == "Um ano a partir da compra."
    assert by_question["xyzzy qwerty"][2] == ()  # a refusal has no context
    # None and NaN are left out of the mean; grounded_rate counts every question.
    assert report.metrics["faithfulness"] == 1.0
    assert report.metrics["context_recall"] == 0.5
    assert report.metrics["grounded_rate"] == pytest.approx(2 / 3, abs=1e-6)
    assert report.config["questions"] == {
        "in_dataset": 3,
        "scored_per_metric": {"faithfulness": 2, "context_recall": 2},
    }
    assert report.config["scorer"] == {"name": "fake", "judge_model": "none"}
    refusal = next(d for d in report.details if d["question"] == "xyzzy qwerty")
    assert refusal["grounded"] is False and refusal["context_documents"] == []


async def test_the_overrides_change_only_this_run(world: World) -> None:
    kb = await make_kb(world)
    report = await AnswerEvaluator(world.deps, FakeScorer(), retrievers=("dense",)).evaluate(
        world.admin, kb, ITEMS[:1]
    )
    assert report.config["knowledge_base_config"]["retrieval"]["retrievers"] == ["dense"]
    stored = await world.deps.repository.get_knowledge_base(world.admin, "vendas")
    assert stored.config.retrieval.retrievers == ("lexical",)


async def test_a_reader_cannot_run_the_evaluation(world: World) -> None:
    from vlade_rag.core.domain import PermissionDenied

    kb = await make_kb(world)
    with pytest.raises(PermissionDenied):
        await AnswerEvaluator(world.deps, FakeScorer()).evaluate(world.reader, kb, ITEMS)


# ------------------------------------------------------------------ RagasScorer


@dataclass
class StubMetric:
    value: Any = 0.75
    error: Exception | None = None

    async def ascore(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return type("Result", (), {"value": self.value})()


def ragas_scorer() -> Any:
    pytest.importorskip("ragas")
    from vlade_rag.evaluation.ragas import RagasScorer

    # No call happens at construction: the client only stores the address and the key.
    return RagasScorer(
        judge_model="judge",
        embeddings_model="embed",
        base_url="http://127.0.0.1:1/v1",
        api_key="test-only",
    )


async def test_ragas_scorer_maps_results_errors_and_nan() -> None:
    scorer = ragas_scorer()
    scorer._faithfulness = StubMetric(0.9)
    scorer._answer_relevancy = StubMetric(float("nan"))
    scorer._context_precision = StubMetric(error=TimeoutError())
    scorer._context_recall = StubMetric(0.4)
    scores = await scorer.score("pergunta", "resposta [1]", ["contexto"], "referência")
    assert scores == {
        "faithfulness": 0.9,
        "answer_relevancy": None,
        "context_precision": None,
        "context_recall": 0.4,
    }
    assert scorer.describe()["errors"] == {"context_precision: TimeoutError": 1}
    assert scorer._context_recall.kwargs == {
        "user_input": "pergunta",
        "retrieved_contexts": ["contexto"],
        "reference": "referência",
    }


async def test_ragas_scorer_skips_the_metrics_it_cannot_compute() -> None:
    scorer = ragas_scorer()
    for name in ("_faithfulness", "_answer_relevancy", "_context_precision", "_context_recall"):
        setattr(scorer, name, StubMetric(0.5))
    without_reference = await scorer.score("p", "r", ["c"], None)
    assert without_reference["context_precision"] is None
    assert without_reference["faithfulness"] == 0.5
    without_context = await scorer.score("p", "r", [], "ref")
    assert without_context == {
        "faithfulness": None,
        "answer_relevancy": 0.5,
        "context_precision": None,
        "context_recall": None,
    }
    assert not math.isnan(without_context["answer_relevancy"])
