"""Query transformers: rewrite, multi-query and HyDE (roadmap 3.2, ADR-0019). No network."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest

from vlade_rag.bootstrap import build_runtime
from vlade_rag.core.config import Settings
from vlade_rag.core.domain import (
    Generation,
    GenerationParams,
    InvalidArgument,
    KnowledgeBase,
    KnowledgeBaseConfig,
    Message,
    ProviderUnavailable,
    Query,
)
from vlade_rag.core.domain.kb_config import GenerationConfig
from vlade_rag.core.ports import QueryTransformer
from vlade_rag.generation.prompts import BuiltinPromptRegistry
from vlade_rag.retrieval.transform import LLMQueryTransformer

pytestmark = pytest.mark.anyio


class ScriptedLLM:
    """Answers with ``reply`` (or raises ``error``) and records each call."""

    name = "scripted"

    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[tuple[Sequence[Message], GenerationParams]] = []

    async def generate(self, messages: Sequence[Message], params: GenerationParams) -> Generation:
        self.calls.append((messages, params))
        if self.error is not None:
            raise self.error
        return Generation(text=self.reply, model=params.model)


def kb(language: str = "pt") -> KnowledgeBase:
    return KnowledgeBase(
        id=uuid4(),
        tenant_id=uuid4(),
        slug="k",
        name="k",
        config=KnowledgeBaseConfig(
            language=language,  # type: ignore[arg-type]
            generation=GenerationConfig(provider="x", model="gen-model"),
        ),
        active_embedding_space_id=uuid4(),
    )


def transformer(mode: Any, llm: ScriptedLLM) -> LLMQueryTransformer:
    return LLMQueryTransformer(mode, lambda cfg: llm, BuiltinPromptRegistry())


async def run(mode: Any, reply: str, *, language: str = "pt") -> tuple[list[Query], ScriptedLLM]:
    llm = ScriptedLLM(reply)
    base = kb(language)
    query = Query("quanto custa o frete?", base.id)
    out = await transformer(mode, llm).transform(None, base, query)  # type: ignore[arg-type]
    return out, llm


async def test_rewrite_keeps_the_original_and_adds_one_query() -> None:
    out, llm = await run("rewrite", '"preço do frete para entrega"\n')
    assert [q.text for q in out] == ["quanto custa o frete?", "preço do frete para entrega"]
    assert all(q.retrievers is None for q in out)  # every retriever reads both
    messages, params = llm.calls[0]
    assert params.model == "gen-model" and params.temperature == 0.0
    # The limit of the base: a reasoning model spends part of it on its thinking.
    assert params.max_output_tokens == kb().config.generation.max_output_tokens
    assert messages[0].role == "system" and "reescreve" in messages[0].content
    assert "quanto custa o frete?" in messages[1].content


async def test_rewrite_uses_only_the_first_line() -> None:
    out, _ = await run("rewrite", "primeira consulta\nsegunda consulta")
    assert [q.text for q in out][1:] == ["primeira consulta"]


async def test_multi_query_strips_bullets_and_numbers_and_keeps_three() -> None:
    reply = "1. custo do frete\n- valor da entrega\n* taxa de envio\n4) quarta variação\n"
    out, _ = await run("multi_query", reply)
    assert [q.text for q in out][1:] == ["custo do frete", "valor da entrega", "taxa de envio"]


async def test_multi_query_drops_repeats_of_the_original_and_of_each_other() -> None:
    reply = "Quanto custa o frete?\ncusto do frete\nCUSTO DO FRETE\n\n"
    out, _ = await run("multi_query", reply)
    assert [q.text for q in out][1:] == ["custo do frete"]


async def test_hyde_joins_the_answer_and_sends_it_only_to_the_dense_retriever() -> None:
    out, _ = await run("hyde", "O frete custa dez reais.\nA entrega leva cinco dias.")
    assert len(out) == 2
    assert out[0].retrievers is None  # the original runs everywhere
    assert out[1].text == "O frete custa dez reais. A entrega leva cinco dias."
    assert out[1].retrievers == ("dense",)


async def test_hyde_is_cut_at_the_limit() -> None:
    out, _ = await run("hyde", "palavra " * 500)
    assert len(out[1].text) <= 1000


@pytest.mark.parametrize("mode", ["rewrite", "multi_query", "hyde"])
async def test_a_provider_failure_gives_back_the_original_query(mode: str) -> None:
    llm = ScriptedLLM(error=ProviderUnavailable("down"))
    base = kb()
    query = Query("pergunta", base.id)
    out = await transformer(mode, llm).transform(None, base, query)  # type: ignore[arg-type]
    assert out == [query]


@pytest.mark.parametrize("mode", ["rewrite", "multi_query", "hyde"])
async def test_an_empty_answer_gives_back_the_original_query(mode: str) -> None:
    out, _ = await run(mode, "  \n\n ")
    assert len(out) == 1


async def test_a_configuration_error_of_the_provider_is_not_hidden() -> None:
    llm = ScriptedLLM(error=InvalidArgument("unknown model"))
    base = kb()
    with pytest.raises(InvalidArgument):
        await transformer("rewrite", llm).transform(None, base, Query("q", base.id))  # type: ignore[arg-type]


async def test_the_english_prompt_is_used_for_an_english_base() -> None:
    _, llm = await run("rewrite", "shipping price", language="en")
    messages, _ = llm.calls[0]
    assert "You rewrite questions" in messages[0].content
    assert messages[1].content.startswith("Question:")


async def test_the_derived_query_respects_the_limit_of_the_server() -> None:
    llm = ScriptedLLM("x" * 100)
    base = kb()
    short = LLMQueryTransformer(
        "rewrite", lambda cfg: llm, BuiltinPromptRegistry(), max_query_chars=10
    )
    out = await short.transform(None, base, Query("q", base.id))  # type: ignore[arg-type]
    assert out[1].text == "x" * 10


def test_an_unknown_mode_is_refused() -> None:
    with pytest.raises(InvalidArgument):
        LLMQueryTransformer("nope", lambda cfg: ScriptedLLM(), BuiltinPromptRegistry())  # type: ignore[arg-type]


async def test_the_prompts_are_versioned_in_both_languages() -> None:
    registry = BuiltinPromptRegistry()
    for name in ("query_rewrite", "query_multi", "query_hyde"):
        for language in ("pt", "en"):
            template = await registry.get(name, language)
            assert template.version == "1" and "{question}" in template.user


async def test_the_runtime_registers_the_three_transformers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VLADE_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_OBJECT_STORAGE__BACKEND", "memory")
    runtime = await build_runtime(Settings(), load_plugins=False)
    try:
        found = runtime.deps.query_transformers
        assert set(found) == {"rewrite", "multi_query", "hyde"}
        assert all(isinstance(t, QueryTransformer) for t in found.values())
        assert set(runtime.deps.lexical_indexes) == {"lexical", "fuzzy", "bm25"}
    finally:
        await runtime.aclose()
