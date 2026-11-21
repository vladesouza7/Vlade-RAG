"""Answer generation with citations (docs/ARCHITECTURE.md sections 11.3 to 11.5 and 12.1).

``AnswerQuery`` prepares the query, runs an engine and records the answer. An engine
(``AnswerEngine``) runs the steps of the flow: retrieve, assemble the context, generate and
validate. ``PipelineEngine`` runs them once, in order. The LangGraph engine
(``vlade_rag.orchestration.langgraph``) adds two conditional edges.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from html import escape
from typing import Protocol

from vlade_rag.core.application import semconv as sc
from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.application.search import Search
from vlade_rag.core.domain import (
    Answer,
    Citation,
    GenerationParams,
    InvalidArgument,
    KnowledgeBase,
    Message,
    Query,
    QueryLogEntry,
    Role,
    ScoredChunk,
    TenantContext,
    TokenUsage,
    parse_filter,
)
from vlade_rag.core.domain.models import JsonValue
from vlade_rag.core.ports import AttrValue, PromptTemplate, Span

_CITATION = re.compile(r"\[(\d{1,3})\]")


# ---------------------------------------------------------------- context


def assemble_context(candidates: Sequence[ScoredChunk], max_tokens: int) -> list[ScoredChunk]:
    """Remove near-duplicates and keep the best chunks inside the token budget.

    A chunk is a near-duplicate when it overlaps more than 50% of an already selected chunk of
    the same document version.
    """
    selected: list[ScoredChunk] = []
    used = 0
    for item in sorted(candidates, key=lambda s: (s.rank, -s.score)):
        chunk = item.chunk
        duplicate = False
        for other in selected:
            o = other.chunk
            if o.document_version_id != chunk.document_version_id:
                continue
            overlap = min(o.end_offset, chunk.end_offset) - max(o.start_offset, chunk.start_offset)
            shorter = min(o.end_offset - o.start_offset, chunk.end_offset - chunk.start_offset)
            if shorter > 0 and overlap / shorter > 0.5:
                duplicate = True
                break
        if duplicate:
            continue
        if used + chunk.token_count > max_tokens and selected:
            break
        selected.append(item)
        used += chunk.token_count
    return selected


def format_sources(context: Sequence[ScoredChunk]) -> str:
    parts = []
    for number, item in enumerate(context, start=1):
        chunk = item.chunk
        page = f' page="{chunk.page}"' if chunk.page is not None else ""
        title = escape(chunk.document_title, quote=True)
        parts.append(f'<source id="{number}" document="{title}"{page}>\n{chunk.text}\n</source>')
    return "\n\n".join(parts)


@dataclass(frozen=True, slots=True)
class ValidatedAnswer:
    text: str
    citations: tuple[Citation, ...]
    grounded: bool
    removed_indexes: tuple[int, ...]


def validate_answer(
    text: str, context: Sequence[ScoredChunk], template: PromptTemplate, require_citations: bool
) -> ValidatedAnswer:
    """Apply section 11.5: drop unknown citation indexes and decide ``grounded``."""
    removed: list[int] = []

    def _keep(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if 1 <= index <= len(context):
            return match.group(0)
        removed.append(index)
        return ""

    cleaned = re.sub(r"[ \t]{2,}", " ", _CITATION.sub(_keep, text)).strip()
    order: list[int] = []
    for match in _CITATION.finditer(cleaned):
        index = int(match.group(1))
        if index not in order:
            order.append(index)
    citations = tuple(
        Citation(
            index=i,
            document_id=context[i - 1].chunk.document_id,
            chunk_id=context[i - 1].chunk.id,
            document_title=context[i - 1].chunk.document_title,
            page=context[i - 1].chunk.page,
            start_offset=context[i - 1].chunk.start_offset,
            end_offset=context[i - 1].chunk.end_offset,
        )
        for i in order
    )
    not_found = template.not_found_answer.rstrip(".").lower()
    says_not_found = not_found in cleaned.lower()
    if not citations and (says_not_found or require_citations):
        return ValidatedAnswer(template.not_found_answer, (), False, tuple(removed))
    return ValidatedAnswer(cleaned, citations, bool(citations), tuple(removed))


# ---------------------------------------------------------------- use case


@dataclass(frozen=True, slots=True)
class AnswerDelta:
    text: str


@dataclass(frozen=True, slots=True)
class AnswerFinal:
    answer: Answer
    replaced: bool  # True when the final text differs from the streamed text


AnswerEvent = AnswerDelta | AnswerFinal


@dataclass(frozen=True, slots=True)
class PreparedQuery:
    """The validated request: the base, the query, the number of chunks and the prompt."""

    kb: KnowledgeBase
    query: Query
    top_k: int
    template: PromptTemplate
    started: float


@dataclass(frozen=True, slots=True)
class Generated:
    text: str
    usage: TokenUsage
    model: str


@dataclass(frozen=True, slots=True)
class Draft:
    """The result of one pass of the flow: the context, the raw text and the validated answer."""

    context: list[ScoredChunk]
    generated: Generated
    validated: ValidatedAnswer


class AnswerEngine(Protocol):
    """Runs the query flow. It yields the streamed text and, last, one ``Draft``."""

    name: str

    def run(
        self, steps: AnswerQuery, ctx: TenantContext, prepared: PreparedQuery, streaming: bool
    ) -> AsyncIterator[AnswerDelta | Draft]: ...


class PipelineEngine:
    """The linear flow of section 11.1: each step runs once, in order. The default engine."""

    name = "pipeline"

    async def run(
        self, steps: AnswerQuery, ctx: TenantContext, prepared: PreparedQuery, streaming: bool
    ) -> AsyncIterator[AnswerDelta | Draft]:
        results = await steps.retrieve(ctx, prepared.kb, prepared.query, prepared.top_k)
        context = steps.assemble(prepared.kb, results)
        generated: Generated | None = None
        async for item in steps.generate(prepared, context, streaming):
            if isinstance(item, Generated):
                generated = item
            else:
                yield item
        if generated is None:  # pragma: no cover - generate always ends with Generated
            raise RuntimeError("The generation step ended without a result.")
        yield Draft(context, generated, steps.validate(prepared, generated.text, context))


class AnswerQuery:
    def __init__(self, deps: Dependencies) -> None:
        self.deps = deps
        self.search = Search(deps)

    async def execute(
        self,
        ctx: TenantContext,
        *,
        knowledge_base: str,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, JsonValue] | None = None,
        language: str | None = None,
    ) -> Answer:
        final: Answer | None = None
        attributes: dict[str, AttrValue] = {
            sc.SPAN_KIND: sc.CHAIN,
            "vlade.knowledge_base": knowledge_base,
        }
        content = self.deps.limits.store_query_text
        if content:
            attributes[sc.INPUT_VALUE] = question
        with self.deps.tracer.span("query", attributes) as span:
            async for event in self._run(
                ctx, knowledge_base, question, top_k, filters, language, False
            ):
                if isinstance(event, AnswerFinal):
                    final = event.answer
            if final is not None:
                span.set_attribute("vlade.grounded", final.grounded)
                if content:
                    span.set_attribute(sc.OUTPUT_VALUE, final.text)
        if final is None:  # pragma: no cover - _run always ends with AnswerFinal
            raise RuntimeError("The answer pipeline ended without a final answer.")
        return final

    def stream(
        self,
        ctx: TenantContext,
        *,
        knowledge_base: str,
        question: str,
        top_k: int | None = None,
        filters: Mapping[str, JsonValue] | None = None,
        language: str | None = None,
    ) -> AsyncIterator[AnswerEvent]:
        return self._run(ctx, knowledge_base, question, top_k, filters, language, True)

    # ------------------------------------------------------------ steps

    async def prepare(
        self,
        ctx: TenantContext,
        knowledge_base: str,
        question: str,
        top_k: int | None,
        filters: Mapping[str, JsonValue] | None,
        language: str | None,
    ) -> PreparedQuery:
        ctx.require(Role.READER)
        started = time.perf_counter()
        kb = await self.deps.repository.get_knowledge_base(ctx, knowledge_base)
        cfg = kb.config
        lang = language or cfg.language
        query = Query(self.search.validate_text(question), kb.id, parse_filter(filters), lang)
        k = self.search.validate_top_k(top_k or cfg.retrieval.rerank.top_n)
        template = await self.deps.prompts.get(cfg.generation.prompt, lang)
        return PreparedQuery(kb, query, k, template, started)

    async def retrieve(
        self, ctx: TenantContext, kb: KnowledgeBase, query: Query, top_k: int
    ) -> list[ScoredChunk]:
        language = query.language or kb.config.language
        content = self.deps.limits.store_query_text
        attributes: dict[str, AttrValue] = {sc.SPAN_KIND: sc.RETRIEVER, "vlade.language": language}
        if content:
            attributes[sc.INPUT_VALUE] = query.text
        with self.deps.tracer.span("query_analysis", attributes) as span:
            results = await self.search.run(ctx, kb, query, top_k)
            for key, value in sc.documents(results, content).items():
                span.set_attribute(key, value)
        return results

    def assemble(self, kb: KnowledgeBase, results: Sequence[ScoredChunk]) -> list[ScoredChunk]:
        with self.deps.tracer.span(
            "context_assembly", {sc.SPAN_KIND: sc.CHAIN, "vlade.candidates": len(results)}
        ):
            return assemble_context(results, kb.config.generation.max_context_tokens)

    async def generate(
        self, prepared: PreparedQuery, context: Sequence[ScoredChunk], streaming: bool
    ) -> AsyncIterator[AnswerDelta | Generated]:
        """Yield the streamed text (when ``streaming``) and, last, the ``Generated`` result.

        Without context, the answer is the "not found" text of the prompt and no LLM runs.
        """
        gen_cfg = prepared.kb.config.generation
        if not context:
            text = prepared.template.not_found_answer
            if streaming:
                yield AnswerDelta(text)
            yield Generated(text, TokenUsage(), gen_cfg.model)
            return
        messages = [
            Message("system", prepared.template.system),
            Message(
                "user",
                prepared.template.render_user(
                    sources=format_sources(context), question=prepared.query.text
                ),
            ),
        ]
        params = GenerationParams(
            model=gen_cfg.model,
            temperature=gen_cfg.temperature,
            max_output_tokens=gen_cfg.max_output_tokens,
        )
        llm = self.deps.llms(gen_cfg)
        attributes: dict[str, AttrValue] = {
            sc.SPAN_KIND: sc.LLM,
            sc.LLM_MODEL_NAME: gen_cfg.model,
            "gen_ai.request.model": gen_cfg.model,
            "vlade.adapter": llm.name,
        }
        if self.deps.limits.store_query_text:
            attributes[sc.INPUT_VALUE] = prepared.query.text
        with self.deps.tracer.span("llm_generation", attributes) as span:
            if streaming:
                usage = TokenUsage()
                parts: list[str] = []
                async for delta in llm.stream(messages, params):
                    if delta.text:
                        parts.append(delta.text)
                        yield AnswerDelta(delta.text)
                    if delta.usage is not None:
                        usage = delta.usage
                result = Generated("".join(parts), usage, gen_cfg.model)
            else:
                generation = await llm.generate(messages, params)
                result = Generated(generation.text, generation.usage, generation.model)
            _record_generation(span, result, self.deps.limits.store_query_text)
        yield result

    def validate(
        self, prepared: PreparedQuery, text: str, context: Sequence[ScoredChunk]
    ) -> ValidatedAnswer:
        with self.deps.tracer.span("response_validation", {sc.SPAN_KIND: sc.CHAIN}) as span:
            validated = validate_answer(
                text,
                context,
                prepared.template,
                prepared.kb.config.generation.require_citations,
            )
            span.set_attribute("vlade.grounded", validated.grounded)
            if validated.removed_indexes:
                span.add_event("citations.removed", {"count": len(validated.removed_indexes)})
        return validated

    # ------------------------------------------------------------ flow

    def engine(self, kb: KnowledgeBase) -> AnswerEngine:
        name = kb.config.orchestration.engine
        engine = self.deps.answer_engines.get(name)
        if engine is not None:
            return engine
        if name == "pipeline":
            return _PIPELINE
        raise InvalidArgument(
            f"The query engine '{name}' is not installed on this server. "
            f"Install the extra '{name}' or set orchestration.engine to 'pipeline'."
        )

    async def _run(
        self,
        ctx: TenantContext,
        knowledge_base: str,
        question: str,
        top_k: int | None,
        filters: Mapping[str, JsonValue] | None,
        language: str | None,
        streaming: bool,
    ) -> AsyncIterator[AnswerEvent]:
        p = await self.prepare(ctx, knowledge_base, question, top_k, filters, language)
        engine = self.engine(p.kb)
        streamed: list[str] = []
        draft: Draft | None = None
        async for item in engine.run(self, ctx, p, streaming):
            if isinstance(item, Draft):
                draft = item
            else:
                streamed.append(item.text)
                yield item
        if draft is None:  # pragma: no cover - an engine always ends with a Draft
            raise RuntimeError(f"The query engine '{engine.name}' ended without an answer.")
        validated = draft.validated
        answer = Answer(
            text=validated.text,
            citations=validated.citations,
            grounded=validated.grounded,
            prompt_name=p.template.name,
            prompt_version=p.template.version,
            model=draft.generated.model,
            usage=draft.generated.usage,
            trace_id=self.deps.tracer.current_trace_id(),
        )
        await self.deps.audit_log.record_query(
            ctx,
            QueryLogEntry(
                interface=ctx.interface,
                mode="query",
                query_hash=hashlib.sha256(p.query.text.encode("utf-8")).digest(),
                result_count=len(draft.context),
                latency_ms=int((time.perf_counter() - p.started) * 1000),
                knowledge_base_id=p.kb.id,
                principal_id=ctx.principal_id,
                query_text=p.query.text if self.deps.limits.store_query_text else None,
                grounded=answer.grounded,
                trace_id=answer.trace_id,
            ),
        )
        # The streamed text is what the client already shows. Without streaming, it is the raw text.
        shown = "".join(streamed) if streaming else draft.generated.text
        yield AnswerFinal(answer, replaced=validated.text != shown)


def _record_generation(span: Span, generated: Generated, with_content: bool) -> None:
    usage = generated.usage
    span.set_attribute(sc.LLM_TOKENS_PROMPT, usage.input_tokens)
    span.set_attribute(sc.LLM_TOKENS_COMPLETION, usage.output_tokens)
    span.set_attribute(sc.LLM_TOKENS_TOTAL, usage.input_tokens + usage.output_tokens)
    if with_content:
        span.set_attribute(sc.OUTPUT_VALUE, generated.text)


_PIPELINE = PipelineEngine()
