"""LangGraph query graph (optional engine, extra ``langgraph``; ARCHITECTURE 12.1, ADR-0023).

The graph runs the same steps as ``PipelineEngine`` (``AnswerQuery.retrieve``, ``assemble``,
``generate`` and ``validate``) and adds two conditional edges:

- After ``retrieve``: when the best result scores below ``orchestration.rewrite_below_score``
  and ``retrieval.query_transform`` is ``none``, the graph rewrites the query once with the
  ``rewrite`` transformer and retrieves again.
- After ``validate``: when the answer is not grounded and an attempt is left
  (``orchestration.max_attempts``), the graph multiplies ``top_k`` by
  ``orchestration.retry_top_k_factor`` and retrieves again.

Without the two edges, the graph gives the same answer as the linear pipeline.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any, Literal, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from vlade_rag.core.application import semconv as sc
from vlade_rag.core.application.answer import (
    AnswerDelta,
    AnswerQuery,
    Draft,
    Generated,
    PreparedQuery,
    ValidatedAnswer,
)
from vlade_rag.core.domain import Query, ScoredChunk, TenantContext

__all__ = ["LangGraphEngine"]


@dataclass(frozen=True, slots=True)
class _Run:
    """The objects of one request. LangGraph passes them to every node (``Runtime.context``)."""

    steps: AnswerQuery
    ctx: TenantContext
    prepared: PreparedQuery
    streaming: bool


class _State(TypedDict, total=False):
    search_query: Query  # the query of the retrievers; the prompt always uses the original
    top_k: int
    attempt: int
    rewritten: bool  # the rewrite ran (at most once per request)
    rewrite_found: bool  # the rewrite gave a new query text
    results: list[ScoredChunk]
    context: list[ScoredChunk]
    generated: Generated
    validated: ValidatedAnswer


async def _retrieve(state: _State, runtime: Runtime[_Run]) -> _State:
    run = runtime.context
    results = await run.steps.retrieve(
        run.ctx, run.prepared.kb, state["search_query"], state["top_k"]
    )
    return {"results": results}


def _after_retrieve(state: _State, runtime: Runtime[_Run]) -> Literal["rewrite", "assemble"]:
    run = runtime.context
    cfg = run.prepared.kb.config
    threshold = cfg.orchestration.rewrite_below_score
    if (
        threshold is None
        or state.get("rewritten", False)
        or cfg.retrieval.query_transform != "none"
        or "rewrite" not in run.steps.deps.query_transformers
    ):
        return "assemble"
    results = state["results"]
    best = max((r.score for r in results), default=None)
    return "rewrite" if best is None or best < threshold else "assemble"


async def _rewrite(state: _State, runtime: Runtime[_Run]) -> _State:
    run = runtime.context
    transformer = run.steps.deps.query_transformers["rewrite"]
    original = run.prepared.query
    with run.steps.deps.tracer.span(
        "query_transform", {sc.SPAN_KIND: sc.CHAIN, "vlade.transform": "rewrite"}
    ) as span:
        queries = await transformer.transform(run.ctx, run.prepared.kb, original)
        derived = [q.text for q in queries if q.text.strip() and q.text != original.text]
        span.set_attribute("vlade.rewritten", bool(derived))
    if not derived:
        return {"rewritten": True, "rewrite_found": False}
    new_query = replace(original, text=derived[0], retrievers=None)
    return {"rewritten": True, "rewrite_found": True, "search_query": new_query}


def _after_rewrite(state: _State) -> Literal["retrieve", "assemble"]:
    # A rewrite without a new text would only repeat the same search.
    return "retrieve" if state.get("rewrite_found", False) else "assemble"


def _assemble(state: _State, runtime: Runtime[_Run]) -> _State:
    run = runtime.context
    return {"context": run.steps.assemble(run.prepared.kb, state["results"])}


async def _generate(state: _State, runtime: Runtime[_Run]) -> _State:
    run = runtime.context
    writer = get_stream_writer() if run.streaming else None
    generated: Generated | None = None
    async for item in run.steps.generate(run.prepared, state["context"], run.streaming):
        if isinstance(item, Generated):
            generated = item
        elif writer is not None:
            writer(item.text)
    if generated is None:  # pragma: no cover - generate always ends with Generated
        raise RuntimeError("The generation step ended without a result.")
    return {"generated": generated}


def _validate(state: _State, runtime: Runtime[_Run]) -> _State:
    run = runtime.context
    validated = run.steps.validate(run.prepared, state["generated"].text, state["context"])
    return {"validated": validated}


def _after_validate(state: _State, runtime: Runtime[_Run]) -> Literal["widen", "__end__"]:
    run = runtime.context
    cfg = run.prepared.kb.config.orchestration
    if state["validated"].grounded or state["attempt"] >= cfg.max_attempts:
        return "__end__"
    if state["top_k"] >= run.steps.deps.limits.max_top_k:
        return "__end__"  # no more chunks are allowed, so a new attempt repeats the same search
    return "widen"


def _widen(state: _State, runtime: Runtime[_Run]) -> _State:
    run = runtime.context
    factor = run.prepared.kb.config.orchestration.retry_top_k_factor
    top_k = min(state["top_k"] * factor, run.steps.deps.limits.max_top_k)
    with run.steps.deps.tracer.span(
        "query_retry",
        {sc.SPAN_KIND: sc.CHAIN, "vlade.attempt": state["attempt"] + 1, "vlade.top_k": top_k},
    ):
        return {"attempt": state["attempt"] + 1, "top_k": top_k}


def _build() -> Any:
    graph = StateGraph(_State, context_schema=_Run)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("rewrite", _rewrite)
    graph.add_node("assemble", _assemble)
    graph.add_node("generate", _generate)
    graph.add_node("validate", _validate)
    graph.add_node("widen", _widen)
    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges("retrieve", _after_retrieve, ["rewrite", "assemble"])
    graph.add_conditional_edges("rewrite", _after_rewrite, ["retrieve", "assemble"])
    graph.add_edge("assemble", "generate")
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges("validate", _after_validate, ["widen", END])
    graph.add_edge("widen", "retrieve")
    return graph.compile(name="vlade_query")


class LangGraphEngine:
    """The query flow as a LangGraph state graph. Select it with ``orchestration.engine``."""

    name = "langgraph"

    def __init__(self) -> None:
        self.graph = _build()

    async def run(
        self, steps: AnswerQuery, ctx: TenantContext, prepared: PreparedQuery, streaming: bool
    ) -> AsyncIterator[AnswerDelta | Draft]:
        initial: _State = {
            "search_query": prepared.query,
            "top_k": prepared.top_k,
            "attempt": 1,
            "rewritten": False,
        }
        final: _State = initial
        async for mode, chunk in self.graph.astream(
            initial,
            context=_Run(steps, ctx, prepared, streaming),
            stream_mode=["custom", "values"],
        ):
            if mode == "custom":
                yield AnswerDelta(chunk)
            else:
                final = chunk
        yield Draft(final["context"], final["generated"], final["validated"])
