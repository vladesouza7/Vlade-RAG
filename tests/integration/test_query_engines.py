"""Query flow engines: the linear pipeline and the LangGraph graph (roadmap 3.5, ADR-0023).

Runs with memory and PostgreSQL (see ``world``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from typing import Any

import pytest

pytest.importorskip("langgraph")

from tests.conftest import World
from vlade_rag.core.application import CreateKnowledgeBase, SubmitIngestion
from vlade_rag.core.application.answer import AnswerFinal, AnswerQuery, PipelineEngine
from vlade_rag.core.domain import (
    Generation,
    GenerationDelta,
    GenerationParams,
    InvalidArgument,
    KnowledgeBase,
    KnowledgeBaseConfig,
    Message,
    Query,
    RawDocument,
    TenantContext,
)
from vlade_rag.core.domain.kb_config import (
    ChunkingConfig,
    EmbeddingsConfig,
    GenerationConfig,
    OrchestrationConfig,
    RetrievalConfig,
)
from vlade_rag.generation.providers.extractive import ExtractiveLLM
from vlade_rag.orchestration import answer_engines
from vlade_rag.orchestration.langgraph import LangGraphEngine

pytestmark = pytest.mark.anyio

DOCS = {
    "garantia.md": "# Garantia\n\nA garantia dos equipamentos é de um ano a partir da compra.",
    "prazos.md": "# Prazos\n\nO prazo de entrega padrão é de cinco dias úteis para todo o país.",
    "pagamento.md": "# Pagamento\n\nAceitamos boleto, cartão de crédito e Pix, em até doze vezes.",
}
QUESTIONS = [
    "Qual é o prazo de entrega?",
    "Como posso pagar a compra?",
    "garantia dos equipamentos",
    "xyzzy qwerty",  # no chunk matches: the answer is the "not found" text
]


async def make_kb(
    world: World,
    retrievers: tuple[str, ...] = ("dense", "lexical"),
    **orchestration: Any,
) -> KnowledgeBase:
    config = KnowledgeBaseConfig(
        chunking=ChunkingConfig(strategy="markdown", max_tokens=40, overlap_tokens=5),
        embeddings=EmbeddingsConfig(provider="hashing", model="hashing-v1", dimension=64),
        retrieval=RetrievalConfig(retrievers=retrievers),  # type: ignore[arg-type]
        generation=GenerationConfig(provider="extractive", model="extractive"),
        orchestration=OrchestrationConfig(**orchestration),
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
    world.deps.answer_engines = answer_engines()
    return created


def with_engine(world: World, engine: Any) -> AnswerQuery:
    """An AnswerQuery that runs ``engine`` whatever the configuration of the base says."""
    answer = AnswerQuery(world.deps)
    answer.engine = lambda kb: engine  # type: ignore[method-assign]
    return answer


async def stream_events(answer: AnswerQuery, ctx: TenantContext, question: str) -> list[Any]:
    return [e async for e in answer.stream(ctx, knowledge_base="vendas", question=question)]


# ------------------------------------------------------------------ equality


async def test_both_engines_give_the_same_answer(world: World) -> None:
    await make_kb(world)
    pipeline, graph = with_engine(world, PipelineEngine()), with_engine(world, LangGraphEngine())
    for question in QUESTIONS:
        expected = await pipeline.execute(world.admin, knowledge_base="vendas", question=question)
        got = await graph.execute(world.admin, knowledge_base="vendas", question=question)
        assert got == expected, question


async def test_both_engines_stream_the_same_events(world: World) -> None:
    await make_kb(world)
    pipeline, graph = with_engine(world, PipelineEngine()), with_engine(world, LangGraphEngine())
    for question in QUESTIONS:
        expected = await stream_events(pipeline, world.admin, question)
        got = await stream_events(graph, world.admin, question)
        assert got == expected, question
        assert len(expected) >= 2  # at least one delta and the final answer


# ------------------------------------------------------------------ selection


async def test_the_configuration_selects_the_engine(world: World) -> None:
    kb = await make_kb(world, engine="langgraph")
    answer = AnswerQuery(world.deps)
    assert answer.engine(kb).name == "langgraph"
    assert answer.engine(replace(kb, config=KnowledgeBaseConfig())).name == "pipeline"


async def test_a_missing_engine_is_an_invalid_argument(world: World) -> None:
    await make_kb(world, engine="langgraph")
    world.deps.answer_engines = {}
    with pytest.raises(InvalidArgument, match="extra 'langgraph'"):
        await AnswerQuery(world.deps).execute(
            world.admin, knowledge_base="vendas", question="garantia"
        )
    # Without any engine registered, the built-in pipeline still runs.
    kb = await world.deps.repository.get_knowledge_base(world.admin, "vendas")
    assert AnswerQuery(world.deps).engine(replace(kb, config=KnowledgeBaseConfig())).name == (
        "pipeline"
    )


# ------------------------------------------------------------------ rewrite edge


class StubRewrite:
    """A ``rewrite`` transformer with a fixed derived query."""

    name = "rewrite"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def transform(self, ctx: TenantContext, kb: KnowledgeBase, query: Query) -> list[Query]:
        self.calls += 1
        return [query, replace(query, text=self.text)]


async def test_a_weak_result_makes_the_graph_rewrite_the_query_once(world: World) -> None:
    await make_kb(world, ("lexical",), engine="langgraph", rewrite_below_score=1e9)
    stub = StubRewrite("garantia dos equipamentos")
    world.deps.query_transformers = {"rewrite": stub}
    answer = await AnswerQuery(world.deps).execute(
        world.admin, knowledge_base="vendas", question="xyzzy qwerty"
    )
    assert answer.grounded
    assert answer.citations[0].document_title == "garantia.md"
    assert stub.calls == 1  # the score stays below the limit, but the rewrite runs only once


async def test_the_pipeline_has_no_rewrite_edge(world: World) -> None:
    await make_kb(world, ("lexical",), engine="pipeline", rewrite_below_score=1e9)
    stub = StubRewrite("garantia dos equipamentos")
    world.deps.query_transformers = {"rewrite": stub}
    answer = await AnswerQuery(world.deps).execute(
        world.admin, knowledge_base="vendas", question="xyzzy qwerty"
    )
    assert not answer.grounded
    assert stub.calls == 0


async def test_a_good_result_skips_the_rewrite(world: World) -> None:
    await make_kb(world, ("lexical",), engine="langgraph", rewrite_below_score=0.0)
    stub = StubRewrite("pagamento")
    world.deps.query_transformers = {"rewrite": stub}
    answer = await AnswerQuery(world.deps).execute(
        world.admin, knowledge_base="vendas", question="garantia dos equipamentos"
    )
    assert answer.citations[0].document_title == "garantia.md"
    assert stub.calls == 0


async def test_a_rewrite_without_new_text_does_not_search_again(world: World) -> None:
    await make_kb(world, ("lexical",), engine="langgraph", rewrite_below_score=1e9)
    stub = StubRewrite("xyzzy qwerty")  # the same text as the question
    world.deps.query_transformers = {"rewrite": stub}
    answer = AnswerQuery(world.deps)
    searches = record_searches(answer)
    result = await answer.execute(world.admin, knowledge_base="vendas", question="xyzzy qwerty")
    assert not result.grounded
    assert searches == [("xyzzy qwerty", 8)]


# ------------------------------------------------------------------ retry edge


class FlakyLLM:
    """Answers without citations for the first ``failures`` calls, then like ExtractiveLLM."""

    name = "flaky"

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0
        self.inner = ExtractiveLLM()

    async def generate(self, messages: Sequence[Message], params: GenerationParams) -> Generation:
        self.calls += 1
        if self.calls <= self.failures:
            return Generation(text="Talvez seja isso.", model=self.name)
        return await self.inner.generate(messages, params)

    async def stream(
        self, messages: Sequence[Message], params: GenerationParams
    ) -> AsyncIterator[GenerationDelta]:
        generation = await self.generate(messages, params)
        yield GenerationDelta(generation.text)


def record_searches(answer: AnswerQuery) -> list[tuple[str, int]]:
    searches: list[tuple[str, int]] = []
    original = answer.retrieve

    async def retrieve(ctx: TenantContext, kb: KnowledgeBase, query: Query, top_k: int) -> Any:
        searches.append((query.text, top_k))
        return await original(ctx, kb, query, top_k)

    answer.retrieve = retrieve  # type: ignore[method-assign]
    return searches


async def test_an_ungrounded_answer_makes_the_graph_retry_with_more_chunks(world: World) -> None:
    await make_kb(world, engine="langgraph", max_attempts=2)
    llm = FlakyLLM(failures=1)
    world.deps.llms = lambda cfg: llm
    answer = AnswerQuery(world.deps)
    searches = record_searches(answer)
    result = await answer.execute(
        world.admin, knowledge_base="vendas", question="garantia dos equipamentos"
    )
    assert result.grounded
    assert llm.calls == 2
    assert searches == [("garantia dos equipamentos", 8), ("garantia dos equipamentos", 16)]


async def test_the_retry_stops_after_the_last_attempt(world: World) -> None:
    await make_kb(world, engine="langgraph", max_attempts=3, retry_top_k_factor=2)
    llm = FlakyLLM(failures=10)
    world.deps.llms = lambda cfg: llm
    answer = AnswerQuery(world.deps)
    searches = record_searches(answer)
    result = await answer.execute(
        world.admin, knowledge_base="vendas", question="garantia dos equipamentos"
    )
    assert not result.grounded
    assert [k for _, k in searches] == [8, 16, 32]


async def test_the_retry_stops_at_the_top_k_limit(world: World) -> None:
    await make_kb(world, engine="langgraph", max_attempts=3, retry_top_k_factor=4)
    llm = FlakyLLM(failures=10)
    world.deps.llms = lambda cfg: llm
    answer = AnswerQuery(world.deps)
    searches = record_searches(answer)
    await answer.execute(world.admin, knowledge_base="vendas", question="garantia")
    assert [k for _, k in searches] == [8, 32, 50]  # 50 is Limits.max_top_k


async def test_a_retried_stream_marks_the_final_text_as_replaced(world: World) -> None:
    await make_kb(world, engine="langgraph", max_attempts=2)
    llm = FlakyLLM(failures=1)
    world.deps.llms = lambda cfg: llm
    events = await stream_events(AnswerQuery(world.deps), world.admin, "garantia dos equipamentos")
    final = events[-1]
    assert isinstance(final, AnswerFinal)
    assert final.answer.grounded
    assert final.replaced  # the client saw the text of the first attempt, too
