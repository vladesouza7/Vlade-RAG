"""Answer generation with citations (docs/ARCHITECTURE.md sections 11.3 to 11.5)."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from html import escape

from vlade_rag.core.application.deps import Dependencies
from vlade_rag.core.application.search import Search
from vlade_rag.core.domain import (
    Answer,
    Citation,
    GenerationParams,
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
from vlade_rag.core.ports import PromptTemplate

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
class _Prepared:
    kb: KnowledgeBase
    query: Query
    context: list[ScoredChunk]
    template: PromptTemplate
    messages: list[Message]
    params: GenerationParams
    started: float


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
        async for event in self._run(
            ctx, knowledge_base, question, top_k, filters, language, False
        ):
            if isinstance(event, AnswerFinal):
                final = event.answer
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

    async def _prepare(
        self,
        ctx: TenantContext,
        knowledge_base: str,
        question: str,
        top_k: int | None,
        filters: Mapping[str, JsonValue] | None,
        language: str | None,
    ) -> _Prepared:
        ctx.require(Role.READER)
        started = time.perf_counter()
        kb = await self.deps.repository.get_knowledge_base(ctx, knowledge_base)
        cfg = kb.config
        lang = language or cfg.language
        query = Query(self.search.validate_text(question), kb.id, parse_filter(filters), lang)
        k = self.search.validate_top_k(top_k or cfg.retrieval.rerank.top_n)
        with self.deps.tracer.span("query_analysis", {"vlade.language": lang}):
            results = await self.search.run(ctx, kb, query, k)
        with self.deps.tracer.span("context_assembly", {"vlade.candidates": len(results)}):
            context = assemble_context(results, cfg.generation.max_context_tokens)
        template = await self.deps.prompts.get(cfg.generation.prompt, lang)
        messages = [
            Message("system", template.system),
            Message(
                "user",
                template.render_user(sources=format_sources(context), question=query.text),
            ),
        ]
        params = GenerationParams(
            model=cfg.generation.model,
            temperature=cfg.generation.temperature,
            max_output_tokens=cfg.generation.max_output_tokens,
        )
        return _Prepared(kb, query, context, template, messages, params, started)

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
        p = await self._prepare(ctx, knowledge_base, question, top_k, filters, language)
        gen_cfg = p.kb.config.generation
        usage = TokenUsage()
        model = gen_cfg.model
        if not p.context:
            raw_text = p.template.not_found_answer
            if streaming:
                yield AnswerDelta(raw_text)
        else:
            llm = self.deps.llms(gen_cfg)
            with self.deps.tracer.span(
                "llm_generation", {"gen_ai.request.model": gen_cfg.model, "vlade.adapter": llm.name}
            ):
                if streaming:
                    parts: list[str] = []
                    async for delta in llm.stream(p.messages, p.params):
                        if delta.text:
                            parts.append(delta.text)
                            yield AnswerDelta(delta.text)
                        if delta.usage is not None:
                            usage = delta.usage
                    raw_text = "".join(parts)
                else:
                    generation = await llm.generate(p.messages, p.params)
                    raw_text, usage, model = generation.text, generation.usage, generation.model
        with self.deps.tracer.span("response_validation") as span:
            validated = validate_answer(raw_text, p.context, p.template, gen_cfg.require_citations)
            span.set_attribute("vlade.grounded", validated.grounded)
            if validated.removed_indexes:
                span.add_event("citations.removed", {"count": len(validated.removed_indexes)})
        answer = Answer(
            text=validated.text,
            citations=validated.citations,
            grounded=validated.grounded,
            prompt_name=p.template.name,
            prompt_version=p.template.version,
            model=model,
            usage=usage,
            trace_id=self.deps.tracer.current_trace_id(),
        )
        await self.deps.audit_log.record_query(
            ctx,
            QueryLogEntry(
                interface=ctx.interface,
                mode="query",
                query_hash=hashlib.sha256(p.query.text.encode("utf-8")).digest(),
                result_count=len(p.context),
                latency_ms=int((time.perf_counter() - p.started) * 1000),
                knowledge_base_id=p.kb.id,
                principal_id=ctx.principal_id,
                query_text=p.query.text if self.deps.limits.store_query_text else None,
                grounded=answer.grounded,
                trace_id=answer.trace_id,
            ),
        )
        yield AnswerFinal(answer, replaced=validated.text != raw_text)
